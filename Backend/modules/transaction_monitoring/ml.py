"""Interface d'inférence ML pour le module Transaction Monitoring.

Le modèle (XGBoost) est entraîné hors ligne par scripts/train_model.py sur le dataset
synthétique. Ce module charge l'artefact entraîné et expose une fonction unique,
`predict`, qui transforme un ContextFeatures (mêmes variables que les règles, cf.
feature_engineering.py) en score 0-100 + facteurs explicatifs (SHAP).
"""

import json
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd
import shap

from modules.transaction_monitoring.feature_engineering import ContextFeatures
from shared.config.constants import CHANNELS, KYC_LEVELS, TRANSACTION_TYPES
from shared.config.settings import settings

NUMERIC_COLUMNS = [
    "amount_xof_equivalent",
    "hour",
    "day_of_week",
    "day_of_month",
    "is_payday_window",
    "account_age_days",
    "has_history",
    "sender_avg_amount_30d",
    "amount_to_avg_ratio",
    "is_known_receiver",
    "tx_count_last_10min",
    "tx_count_last_1h",
    "sum_amount_last_1h",
    "distinct_receivers_last_1h",
    "is_batch_operation",
    "batch_size_so_far",
    "batch_unknown_receiver_ratio",
    "is_cross_border",
    "minutes_since_last_incoming",
    "incoming_amount_ratio",
    "is_cross_border_passthrough",
    "is_new_device",
    "is_balance_drained",
    "agent_tx_count_last_1h",
    "agent_distinct_senders_last_1h",
]
CATEGORICAL_COLUMNS = {
    "kyc_level": KYC_LEVELS,
    "transaction_type": TRANSACTION_TYPES,
    "channel": CHANNELS,
}

# Traduction technique -> libellé lisible pour les raisons générées à partir de SHAP
HUMAN_LABELS = {
    "amount_xof_equivalent": "Montant de la transaction",
    "hour": "Heure de la transaction",
    "day_of_week": "Jour de la semaine",
    "day_of_month": "Jour du mois",
    "is_payday_window": "Période de paie / fin de mois",
    "account_age_days": "Ancienneté du compte",
    "has_history": "Absence d'historique client",
    "sender_avg_amount_30d": "Montant moyen habituel du client",
    "amount_to_avg_ratio": "Écart du montant par rapport à l'habitude",
    "is_known_receiver": "Bénéficiaire non habituel",
    "tx_count_last_10min": "Fréquence de transactions (10 min)",
    "tx_count_last_1h": "Fréquence de transactions (1h)",
    "sum_amount_last_1h": "Cumul des montants (1h)",
    "distinct_receivers_last_1h": "Diversité des bénéficiaires (1h)",
    "is_batch_operation": "Fait partie d'un paiement de masse déclaré",
    "batch_size_so_far": "Taille du lot de paiement de masse",
    "batch_unknown_receiver_ratio": "Part de bénéficiaires inconnus dans le lot",
    "is_cross_border": "Transfert international",
    "minutes_since_last_incoming": "Délai depuis la dernière réception d'argent",
    "incoming_amount_ratio": "Ressemblance avec un montant reçu récemment",
    "is_cross_border_passthrough": "Schéma de transit transfrontalier",
    "is_new_device": "Nouvel appareil jamais utilisé",
    "is_balance_drained": "Solde vidé après la transaction",
    "agent_tx_count_last_1h": "Volume de retraits traités par l'agent (1h)",
    "agent_distinct_senders_last_1h": "Diversité de clients chez l'agent (1h)",
}

CATEGORICAL_BASE_LABELS = {
    "kyc_level": "Niveau KYC",
    "transaction_type": "Type de transaction",
    "channel": "Canal utilisé",
}


def context_to_raw_row(features: ContextFeatures) -> dict:
    row = {col: getattr(features, col) for col in NUMERIC_COLUMNS}
    row["has_history"] = int(row["has_history"])
    row["is_known_receiver"] = int(row["is_known_receiver"])
    row["is_payday_window"] = int(row["is_payday_window"])
    row["is_batch_operation"] = int(row["is_batch_operation"])
    row["is_cross_border"] = int(row["is_cross_border"])
    row["is_cross_border_passthrough"] = int(row["is_cross_border_passthrough"])
    row["is_new_device"] = int(row["is_new_device"])
    row["is_balance_drained"] = int(row["is_balance_drained"])
    row["kyc_level"] = features.kyc_level
    row["transaction_type"] = features.transaction_type
    row["channel"] = features.channel
    return row


def vectorize_rows(rows: list[dict], feature_columns: list[str]) -> pd.DataFrame:
    """Transforme une liste de dict bruts (numériques + catégoriels) en matrice one-hot
    alignée sur `feature_columns` (les colonnes vues à l'entraînement)."""

    df = pd.DataFrame(rows)
    df = pd.get_dummies(df, columns=list(CATEGORICAL_COLUMNS.keys()))
    for col in feature_columns:
        if col not in df.columns:
            df[col] = 0
    return df[feature_columns]


class ModelBundle:
    def __init__(self, model, feature_columns: list[str], metadata: dict):
        self.model = model
        self.feature_columns = feature_columns
        self.metadata = metadata
        self.explainer = shap.TreeExplainer(model)

    def predict(self, features: ContextFeatures) -> tuple[float, list[str]]:
        row = context_to_raw_row(features)
        X = vectorize_rows([row], self.feature_columns)
        proba = float(self.model.predict_proba(X)[0, 1])
        ml_score = round(proba * 100, 2)

        shap_values = self.explainer.shap_values(X)
        contributions = list(zip(self.feature_columns, shap_values[0]))
        contributions.sort(key=lambda item: abs(item[1]), reverse=True)
        top_factors = [
            _describe_factor(col, val)
            for col, val in contributions[:3]
            if abs(val) > 1e-4
        ]
        return ml_score, top_factors


def _describe_factor(column: str, shap_value: float) -> str:
    sign = "+" if shap_value > 0 else "-"
    for base, label in CATEGORICAL_BASE_LABELS.items():
        prefix = base + "_"
        if column.startswith(prefix):
            value = column[len(prefix):]
            return f"{label} : {value} (impact {sign})"
    label = HUMAN_LABELS.get(column, column)
    return f"{label} (impact {sign})"


@lru_cache(maxsize=1)
def get_model_bundle() -> ModelBundle:
    model = joblib.load(settings.ml_model_path)
    with open(settings.ml_feature_list_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    return ModelBundle(model, payload["feature_columns"], payload.get("metadata", {}))

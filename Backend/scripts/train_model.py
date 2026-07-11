"""Entraîne le modèle XGBoost du module Transaction Monitoring sur le dataset synthétique.

Pipeline : charge data/transactions.csv + data/customers.csv, recalcule pour chaque
transaction les variables "point-in-time" (mêmes règles que repository.py en production,
via feature_engineering.compute_context_features), entraîne un classifieur XGBoost,
évalue (AUC-ROC, AUC-PR, precision/recall) et sauvegarde le modèle + la liste de
colonnes + les métriques dans ml_models/.

Usage:
    python scripts/train_model.py
"""

import bisect
import json
import sys
from collections import deque
from datetime import timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from modules.transaction_monitoring.feature_engineering import (  # noqa: E402
    HistoryEntry,
    IncomingEntry,
    compute_context_features,
)
from modules.transaction_monitoring.ml import (  # noqa: E402
    CATEGORICAL_COLUMNS,
    context_to_raw_row,
)
from shared.utils.currency import to_xof_equivalent  # noqa: E402
from shared.utils.phone import country_from_phone  # noqa: E402

HISTORY_WINDOW_DAYS = 30


def build_incoming_index(transactions: pd.DataFrame) -> dict[str, tuple[list, list]]:
    """Index global (tous émetteurs confondus) des transactions reçues par chaque
    numéro, trié par date, pour retrouver rapidement (recherche binaire) la dernière
    transaction entrante avant un instant donné — utilisé pour la détection de transit
    transfrontalier (reçu d'un pays, renvoyé vers un autre)."""
    index: dict[str, tuple[list, list]] = {}
    for receiver_phone, group in transactions.groupby("receiver_phone", sort=False):
        group = group.sort_values("timestamp")
        timestamps = list(group["timestamp"])
        entries = [
            IncomingEntry(
                sender_country=country_from_phone(row.sender_phone),
                amount_xof_equivalent=to_xof_equivalent(row.amount, row.currency),
                created_at=row.timestamp,
                transaction_type=row.transaction_type,
            )
            for row in group.itertuples()
        ]
        index[receiver_phone] = (timestamps, entries)
    return index


def build_agent_index(transactions: pd.DataFrame) -> dict[str, tuple[list, list]]:
    """Index global des transactions par agent (triées par date), pour calculer en
    O(log n) le volume et la diversité de clients traités par un agent dans l'heure
    précédente (cf. rules.AGENT_COLLUSION_CASHOUT)."""
    index: dict[str, tuple[list, list]] = {}
    agent_txs = transactions[transactions["agent_id"].notna()]
    for agent_id, group in agent_txs.groupby("agent_id", sort=False):
        group = group.sort_values("timestamp")
        index[agent_id] = (list(group["timestamp"]), list(group["sender_phone"]))
    return index


def agent_recent_activity(agent_id, timestamp, agent_index: dict) -> tuple[int, int]:
    if not isinstance(agent_id, str) or agent_id not in agent_index:
        return 0, 0
    timestamps, senders = agent_index[agent_id]
    window_start = timestamp - timedelta(hours=1)
    lo = bisect.bisect_left(timestamps, window_start)
    hi = bisect.bisect_left(timestamps, timestamp)
    return hi - lo, len(set(senders[lo:hi]))


def build_feature_dataset(transactions: pd.DataFrame) -> pd.DataFrame:
    """Rejoue chaque client en ordre chronologique avec une fenêtre glissante de 30
    jours (deque) pour calculer les variables sans jamais regarder le futur."""

    incoming_index = build_incoming_index(transactions)
    agent_index = build_agent_index(transactions)
    rows = []
    for sender_phone, group in transactions.groupby("sender_phone", sort=False):
        group = group.sort_values("timestamp")
        account_created_at = group["account_created_at"].iloc[0]
        kyc_level = group["kyc_level"].iloc[0]
        sender_country = group["country"].iloc[0]
        window: deque[HistoryEntry] = deque()
        timestamps_in, entries_in = incoming_index.get(sender_phone, ([], []))

        for tx in group.itertuples():
            cutoff = tx.timestamp - timedelta(days=HISTORY_WINDOW_DAYS)
            while window and window[0].created_at < cutoff:
                window.popleft()

            idx = bisect.bisect_left(timestamps_in, tx.timestamp)
            incoming_history = [entries_in[idx - 1]] if idx > 0 else []
            receiver_country = country_from_phone(tx.receiver_phone)
            batch_id = tx.batch_id if isinstance(tx.batch_id, str) else None
            device_id = tx.device_id if isinstance(tx.device_id, str) else None
            balance_after_sender = (
                tx.balance_after_sender if pd.notna(tx.balance_after_sender) else None
            )
            agent_tx_count_last_1h, agent_distinct_senders_last_1h = agent_recent_activity(
                tx.agent_id, tx.timestamp, agent_index
            )

            features = compute_context_features(
                amount=tx.amount,
                receiver_phone=tx.receiver_phone,
                timestamp=tx.timestamp,
                transaction_type=tx.transaction_type,
                channel=tx.channel,
                currency=tx.currency,
                account_created_at=account_created_at,
                kyc_level=kyc_level,
                prior_history=list(window),
                sender_country=sender_country,
                receiver_country=receiver_country,
                batch_id=batch_id,
                incoming_history=incoming_history,
                device_id=device_id,
                balance_after_sender=balance_after_sender,
                agent_tx_count_last_1h=agent_tx_count_last_1h,
                agent_distinct_senders_last_1h=agent_distinct_senders_last_1h,
            )
            row = context_to_raw_row(features)
            row["is_fraud"] = tx.is_fraud
            rows.append(row)

            window.append(
                HistoryEntry(
                    receiver_phone=tx.receiver_phone,
                    amount_xof_equivalent=to_xof_equivalent(tx.amount, tx.currency),
                    created_at=tx.timestamp,
                    batch_id=batch_id,
                    device_id=device_id,
                )
            )

    return pd.DataFrame(rows)


def main():
    data_dir = BASE_DIR / "data"
    # dtype=str sur les colonnes téléphone : sinon pandas infère un type numérique et
    # perd le "+" de l'indicatif (ex: "+22505..." devient l'entier 22505...).
    customers = pd.read_csv(
        data_dir / "customers.csv", parse_dates=["account_created_at"], dtype={"phone": str}
    )
    transactions = pd.read_csv(
        data_dir / "transactions.csv",
        parse_dates=["timestamp"],
        dtype={"sender_phone": str, "receiver_phone": str, "batch_id": str, "agent_id": str, "device_id": str},
    )

    transactions = transactions.merge(
        customers[["phone", "account_created_at", "kyc_level", "country"]],
        left_on="sender_phone",
        right_on="phone",
        how="left",
    )

    # Certaines transactions ont un émetteur hors de notre base clients (ex : la jambe
    # entrante du scénario cross_border_passthrough, où un tiers étranger envoie au
    # client cible — volontairement pas un client suivi). Sans ce repli, account_age_days
    # deviendrait NaN et is_cross_border serait calculé sur un pays manquant. On applique
    # le même repli qu'en production pour un client inconnu (repository.get_or_create_customer) :
    # compte considéré "vu pour la première fois maintenant", KYC de base, pays déduit du numéro.
    missing_sender = transactions["phone"].isna()
    transactions.loc[missing_sender, "account_created_at"] = transactions.loc[missing_sender, "timestamp"]
    transactions.loc[missing_sender, "kyc_level"] = "basic"
    transactions.loc[missing_sender, "country"] = transactions.loc[missing_sender, "sender_phone"].map(country_from_phone)

    print("Calcul des variables point-in-time (règles + ML partagent la même logique)...")
    dataset = build_feature_dataset(transactions)

    y = dataset.pop("is_fraud")
    X = pd.get_dummies(dataset, columns=list(CATEGORICAL_COLUMNS.keys()))
    feature_columns = list(X.columns)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    scale_pos_weight = (y_train == 0).sum() / max((y_train == 1).sum(), 1)
    model = XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="aucpr",
        scale_pos_weight=scale_pos_weight,
        random_state=42,
    )
    model.fit(X_train, y_train)

    proba_test = model.predict_proba(X_test)[:, 1]
    pred_test = (proba_test >= 0.5).astype(int)

    auc_roc = roc_auc_score(y_test, proba_test)
    auc_pr = average_precision_score(y_test, proba_test)
    report = classification_report(y_test, pred_test, output_dict=True)
    cm = confusion_matrix(y_test, pred_test).tolist()

    print(f"\nAUC-ROC : {auc_roc:.4f}")
    print(f"AUC-PR  : {auc_pr:.4f}")
    print(classification_report(y_test, pred_test))
    print("Matrice de confusion (lignes=réel, colonnes=prédit) :")
    print(cm)

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_test.sample(min(2000, len(X_test)), random_state=42))
    global_importance = (
        pd.Series(np.abs(shap_values).mean(axis=0), index=feature_columns)
        .sort_values(ascending=False)
        .head(10)
    )
    print("\nTop 10 variables les plus influentes (SHAP, moyenne |impact|) :")
    print(global_importance)

    ml_models_dir = BASE_DIR / "ml_models"
    ml_models_dir.mkdir(exist_ok=True)
    joblib.dump(model, ml_models_dir / "transaction_risk_model.joblib")

    metadata = {
        "model_version": "txn-monitoring-v1",
        "trained_at": pd.Timestamp.utcnow().isoformat(),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "fraud_rate_train": float(y_train.mean()),
        "metrics": {
            "auc_roc": auc_roc,
            "auc_pr": auc_pr,
            "confusion_matrix": cm,
            "classification_report": report,
        },
        "top_features": global_importance.to_dict(),
    }
    with open(ml_models_dir / "feature_columns.json", "w", encoding="utf-8") as fh:
        json.dump({"feature_columns": feature_columns, "metadata": metadata}, fh, indent=2)

    print(f"\nModèle sauvegardé -> {ml_models_dir / 'transaction_risk_model.joblib'}")
    print(f"Colonnes + métadonnées -> {ml_models_dir / 'feature_columns.json'}")


if __name__ == "__main__":
    main()

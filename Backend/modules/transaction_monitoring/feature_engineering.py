"""Calcul des variables contextuelles utilisées à la fois par les règles et par le modèle ML.

Ce module est la source unique de vérité pour la logique "point-in-time" :
- à l'entraînement (scripts/train_model.py), on rejoue l'historique chronologique et on ne
  regarde jamais une transaction future par rapport à la transaction courante ;
- en production (repository.py), on interroge la base pour l'historique réel du client.

Centraliser cette logique évite le "train/serve skew" (le modèle voit à l'entraînement
exactement les mêmes variables qu'au moment de noter une transaction en direct).

Multi-devises : tous les montants utilisés pour le scoring (ratios, seuils, historique,
feature ML) sont normalisés en équivalent XOF via shared/utils/currency.py, pour qu'un
seuil ait le même sens réel qu'il s'agisse de XOF, NGN ou GHS. Le montant brut et la
devise d'origine (`amount`, `currency`) restent disponibles pour l'affichage/l'audit.
"""

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta

from shared.utils.currency import to_xof_equivalent

# Fenêtre de recherche d'une transaction entrante récente pour détecter un schéma de
# transit ("passthrough") : reçu puis renvoyé très vite vers un autre pays.
PASSTHROUGH_WINDOW_MINUTES = 60
PASSTHROUGH_AMOUNT_RATIO_RANGE = (0.7, 1.3)
NO_INCOMING_SENTINEL_MINUTES = 999_999.0

# Solde après transaction considéré comme "compte vidé" (équivalent XOF, proche de zéro).
BALANCE_DRAINED_THRESHOLD_XOF = 500.0

# Nombre minimum de bénéficiaires déjà vus dans le lot avant d'évaluer si CE lot précis
# est suspect (évite un faux positif sur la toute première transaction d'un lot légitime).
BATCH_MIN_LEGS_BEFORE_CHECK = 3


@dataclass
class HistoryEntry:
    receiver_phone: str
    amount_xof_equivalent: float
    created_at: datetime
    batch_id: str | None = None
    device_id: str | None = None


@dataclass
class IncomingEntry:
    """Transaction reçue par le client (lui en tant que destinataire), utilisée pour
    détecter un schéma de transit transfrontalier (reçu d'un pays, renvoyé vers un autre)."""

    sender_country: str | None
    amount_xof_equivalent: float
    created_at: datetime


def is_payday_window(timestamp: datetime) -> bool:
    """Fenêtre de paie / fin de mois (5 premiers jours et 5 derniers jours du mois) :
    période où les flux Mobile Money augmentent structurellement en Afrique de l'Ouest
    (versement des salaires, loyers, factures). Sert à la fois à injecter ce pattern
    dans le dataset synthétique (scripts/generate_synthetic_data.py) et à le calculer en
    production, pour que le modèle apprenne à ne pas confondre un pic de paie normal
    avec une anomalie."""
    _, days_in_month = calendar.monthrange(timestamp.year, timestamp.month)
    return timestamp.day <= 5 or timestamp.day > days_in_month - 5


@dataclass
class ContextFeatures:
    amount: float
    currency: str
    amount_xof_equivalent: float
    hour: int
    day_of_week: int
    day_of_month: int
    is_payday_window: bool
    account_age_days: float
    has_history: bool
    sender_avg_amount_30d: float
    amount_to_avg_ratio: float
    is_known_receiver: bool
    tx_count_last_10min: int
    tx_count_last_1h: int
    sum_amount_last_1h: float
    distinct_receivers_last_1h: int
    is_batch_operation: bool
    batch_size_so_far: int
    batch_unknown_receiver_ratio: float
    is_cross_border: bool
    minutes_since_last_incoming: float
    incoming_amount_ratio: float
    is_cross_border_passthrough: bool
    is_new_device: bool
    is_balance_drained: bool
    agent_tx_count_last_1h: int
    agent_distinct_senders_last_1h: int
    kyc_level: str
    transaction_type: str
    channel: str

    def to_dict(self) -> dict:
        return {
            "amount_xof_equivalent": self.amount_xof_equivalent,
            "hour": self.hour,
            "day_of_week": self.day_of_week,
            "day_of_month": self.day_of_month,
            "is_payday_window": self.is_payday_window,
            "account_age_days": self.account_age_days,
            "has_history": self.has_history,
            "sender_avg_amount_30d": self.sender_avg_amount_30d,
            "amount_to_avg_ratio": self.amount_to_avg_ratio,
            "is_known_receiver": self.is_known_receiver,
            "tx_count_last_10min": self.tx_count_last_10min,
            "tx_count_last_1h": self.tx_count_last_1h,
            "sum_amount_last_1h": self.sum_amount_last_1h,
            "distinct_receivers_last_1h": self.distinct_receivers_last_1h,
            "is_batch_operation": self.is_batch_operation,
            "batch_size_so_far": self.batch_size_so_far,
            "batch_unknown_receiver_ratio": self.batch_unknown_receiver_ratio,
            "is_cross_border": self.is_cross_border,
            "minutes_since_last_incoming": self.minutes_since_last_incoming,
            "incoming_amount_ratio": self.incoming_amount_ratio,
            "is_cross_border_passthrough": self.is_cross_border_passthrough,
            "is_new_device": self.is_new_device,
            "is_balance_drained": self.is_balance_drained,
            "agent_tx_count_last_1h": self.agent_tx_count_last_1h,
            "agent_distinct_senders_last_1h": self.agent_distinct_senders_last_1h,
            "kyc_level": self.kyc_level,
            "transaction_type": self.transaction_type,
            "channel": self.channel,
        }


def compute_context_features(
    *,
    amount: float,
    receiver_phone: str,
    timestamp: datetime,
    transaction_type: str,
    channel: str,
    account_created_at: datetime,
    kyc_level: str,
    prior_history: list[HistoryEntry],
    currency: str = "XOF",
    sender_country: str | None = None,
    receiver_country: str | None = None,
    batch_id: str | None = None,
    incoming_history: list[IncomingEntry] | None = None,
    device_id: str | None = None,
    balance_after_sender: float | None = None,
    agent_tx_count_last_1h: int = 0,
    agent_distinct_senders_last_1h: int = 0,
) -> ContextFeatures:
    """prior_history doit contenir uniquement les transactions du même émetteur
    strictement antérieures à `timestamp` (triées ou non, peu importe ici), avec des
    montants déjà normalisés en équivalent XOF (HistoryEntry.amount_xof_equivalent).
    incoming_history : transactions reçues par ce client (lui en tant que destinataire),
    utilisée uniquement pour la détection de transit transfrontalier."""

    incoming_history = incoming_history or []
    amount_xof_equivalent = to_xof_equivalent(amount, currency)

    window_30d = timestamp - timedelta(days=30)
    window_1h = timestamp - timedelta(hours=1)
    window_10min = timestamp - timedelta(minutes=10)

    past_30d = [h for h in prior_history if window_30d <= h.created_at < timestamp]
    # Les transactions qui font partie du même lot déclaré (paiement de masse) ne
    # comptent pas comme des événements de vélocité/fan-out distincts : un envoi groupé
    # à 10 bénéficiaires est une opération légitime unique, pas 10 signaux de risque.
    past_1h = [
        h
        for h in prior_history
        if window_1h <= h.created_at < timestamp and not (batch_id and h.batch_id == batch_id)
    ]
    past_10min = [
        h
        for h in prior_history
        if window_10min <= h.created_at < timestamp and not (batch_id and h.batch_id == batch_id)
    ]

    has_history = len(prior_history) > 0
    sender_avg_amount_30d = (
        sum(h.amount_xof_equivalent for h in past_30d) / len(past_30d) if past_30d else 0.0
    )
    amount_to_avg_ratio = (
        amount_xof_equivalent / sender_avg_amount_30d if sender_avg_amount_30d > 0 else 0.0
    )

    known_receivers = {h.receiver_phone for h in prior_history}
    is_known_receiver = receiver_phone in known_receivers

    account_age_days = max((timestamp - account_created_at).total_seconds() / 86400, 0.0)

    is_cross_border = bool(
        sender_country and receiver_country and sender_country != receiver_country
    )

    # Transit transfrontalier : la transaction entrante la plus récente (avant `timestamp`)
    past_incoming = [h for h in incoming_history if h.created_at < timestamp]
    minutes_since_last_incoming = NO_INCOMING_SENTINEL_MINUTES
    incoming_amount_ratio = 0.0
    is_cross_border_passthrough = False
    if past_incoming:
        last_incoming = max(past_incoming, key=lambda h: h.created_at)
        minutes_since_last_incoming = (timestamp - last_incoming.created_at).total_seconds() / 60
        if last_incoming.amount_xof_equivalent > 0:
            incoming_amount_ratio = amount_xof_equivalent / last_incoming.amount_xof_equivalent
        same_amount = (
            PASSTHROUGH_AMOUNT_RATIO_RANGE[0] <= incoming_amount_ratio <= PASSTHROUGH_AMOUNT_RATIO_RANGE[1]
        )
        different_country = (
            last_incoming.sender_country is not None
            and receiver_country is not None
            and last_incoming.sender_country != receiver_country
        )
        is_cross_border_passthrough = (
            minutes_since_last_incoming <= PASSTHROUGH_WINDOW_MINUTES
            and same_amount
            and different_country
        )

    # Un lot déclaré (paiement de masse) n'est pas automatiquement légitime : un compte
    # compromis peut détourner ce mécanisme pour disperser des fonds vers des comptes
    # mules sous couvert d'une opération "groupée". On évalue la part de bénéficiaires du
    # lot en cours qui n'étaient pas déjà connus du client EN DEHORS de ce lot (un vrai
    # virement de paie répète généralement les mêmes employés/fournisseurs).
    batch_size_so_far = 0
    batch_unknown_receiver_ratio = 0.0
    if batch_id:
        non_batch_known_receivers = {
            h.receiver_phone for h in prior_history if h.batch_id != batch_id
        }
        batch_receivers = [h.receiver_phone for h in prior_history if h.batch_id == batch_id]
        batch_receivers.append(receiver_phone)
        batch_size_so_far = len(batch_receivers)
        unknown_count = sum(1 for r in batch_receivers if r not in non_batch_known_receivers)
        batch_unknown_receiver_ratio = unknown_count / batch_size_so_far

    # Changement d'appareil brutal sur un compte établi : signal SIM swap / prise de
    # contrôle de compte (module SIM Swap Intelligence de la roadmap, simplifié ici).
    known_devices = {h.device_id for h in prior_history if h.device_id}
    is_new_device = bool(has_history and device_id and device_id not in known_devices)

    # Compte vidé après la transaction : signal documenté par les travaux de référence
    # sur la simulation Mobile Money (PaySim, MoMTSim) comme fortement prédictif de
    # fraude/compromission. Optionnel : uniquement si le système appelant transmet le
    # solde (Novaris ne gère pas les soldes lui-même).
    is_balance_drained = bool(
        balance_after_sender is not None
        and balance_after_sender >= 0
        and to_xof_equivalent(balance_after_sender, currency) < BALANCE_DRAINED_THRESHOLD_XOF
        and amount_xof_equivalent > BALANCE_DRAINED_THRESHOLD_XOF
    )

    return ContextFeatures(
        amount=amount,
        currency=currency,
        amount_xof_equivalent=amount_xof_equivalent,
        hour=timestamp.hour,
        day_of_week=timestamp.weekday(),
        day_of_month=timestamp.day,
        is_payday_window=is_payday_window(timestamp),
        account_age_days=account_age_days,
        has_history=has_history,
        sender_avg_amount_30d=sender_avg_amount_30d,
        amount_to_avg_ratio=amount_to_avg_ratio,
        is_known_receiver=is_known_receiver,
        tx_count_last_10min=len(past_10min),
        tx_count_last_1h=len(past_1h),
        sum_amount_last_1h=sum(h.amount_xof_equivalent for h in past_1h),
        distinct_receivers_last_1h=len({h.receiver_phone for h in past_1h}),
        is_batch_operation=batch_id is not None,
        batch_size_so_far=batch_size_so_far,
        batch_unknown_receiver_ratio=batch_unknown_receiver_ratio,
        is_cross_border=is_cross_border,
        minutes_since_last_incoming=minutes_since_last_incoming,
        incoming_amount_ratio=incoming_amount_ratio,
        is_cross_border_passthrough=is_cross_border_passthrough,
        is_new_device=is_new_device,
        is_balance_drained=is_balance_drained,
        agent_tx_count_last_1h=agent_tx_count_last_1h,
        agent_distinct_senders_last_1h=agent_distinct_senders_last_1h,
        kyc_level=kyc_level,
        transaction_type=transaction_type,
        channel=channel,
    )

"""Calcul des variables contextuelles utilisées à la fois par les règles et par le modèle ML.

Ce module est la source unique de vérité pour la logique "point-in-time" :
- à l'entraînement (scripts/train_model.py), on rejoue l'historique chronologique et on ne
  regarde jamais une transaction future par rapport à la transaction courante ;
- en production (repository.py), on interroge la base pour l'historique réel du client.

Centraliser cette logique évite le "train/serve skew" (le modèle voit à l'entraînement
exactement les mêmes variables qu'au moment de noter une transaction en direct).
"""

import calendar
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class HistoryEntry:
    receiver_phone: str
    amount: float
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
    kyc_level: str
    transaction_type: str
    channel: str

    def to_dict(self) -> dict:
        return {
            "amount": self.amount,
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
) -> ContextFeatures:
    """prior_history doit contenir uniquement les transactions du même émetteur
    strictement antérieures à `timestamp` (triées ou non, peu importe ici)."""

    window_30d = timestamp - timedelta(days=30)
    window_1h = timestamp - timedelta(hours=1)
    window_10min = timestamp - timedelta(minutes=10)

    past_30d = [h for h in prior_history if window_30d <= h.created_at < timestamp]
    past_1h = [h for h in prior_history if window_1h <= h.created_at < timestamp]
    past_10min = [h for h in prior_history if window_10min <= h.created_at < timestamp]

    has_history = len(prior_history) > 0
    sender_avg_amount_30d = (
        sum(h.amount for h in past_30d) / len(past_30d) if past_30d else 0.0
    )
    amount_to_avg_ratio = (
        amount / sender_avg_amount_30d if sender_avg_amount_30d > 0 else 0.0
    )

    known_receivers = {h.receiver_phone for h in prior_history}
    is_known_receiver = receiver_phone in known_receivers

    account_age_days = max((timestamp - account_created_at).total_seconds() / 86400, 0.0)

    return ContextFeatures(
        amount=amount,
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
        sum_amount_last_1h=sum(h.amount for h in past_1h),
        distinct_receivers_last_1h=len({h.receiver_phone for h in past_1h}),
        kyc_level=kyc_level,
        transaction_type=transaction_type,
        channel=channel,
    )

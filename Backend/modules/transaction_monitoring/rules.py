"""Moteur de règles métier pour le module Transaction Monitoring.

Chaque règle est déterministe, auditable et documentée : elle produit un code, un poids
(contribution au score 0-100) et une raison lisible par un analyste. Les règles servent de
garde-fou explicable en complément du modèle ML (cf. shared/config/settings.py:
critical_rule_score_floor).
"""

from dataclasses import dataclass

from modules.transaction_monitoring.feature_engineering import ContextFeatures

NIGHT_HOURS = set(range(0, 5))
STRUCTURING_CEILING = 500_000.0
LARGE_AMOUNT_THRESHOLD = 100_000.0


@dataclass
class RuleResult:
    code: str
    description: str
    weight: float
    triggered: bool


def _r_amount_spike(f: ContextFeatures) -> RuleResult:
    ratio = f.amount_to_avg_ratio
    triggered = f.has_history and f.sender_avg_amount_30d > 0 and ratio >= 5
    desc = (
        f"Montant de {f.amount:,.0f} XOF = {ratio:.1f}x la moyenne habituelle du "
        f"client ({f.sender_avg_amount_30d:,.0f} XOF sur 30 jours)"
    )
    return RuleResult("AMOUNT_SPIKE", desc, 35.0, triggered)


def _r_high_velocity(f: ContextFeatures) -> RuleResult:
    triggered = f.tx_count_last_10min >= 3
    desc = f"{f.tx_count_last_10min} transactions du même client en moins de 10 minutes"
    return RuleResult("HIGH_VELOCITY", desc, 30.0, triggered)


def _r_unknown_receiver_high_amount(f: ContextFeatures) -> RuleResult:
    triggered = not f.is_known_receiver and f.amount >= LARGE_AMOUNT_THRESHOLD
    desc = (
        f"Bénéficiaire jamais utilisé par ce client pour un montant de "
        f"{f.amount:,.0f} XOF"
    )
    return RuleResult("UNKNOWN_RECEIVER_HIGH_AMOUNT", desc, 25.0, triggered)


def _r_night_activity(f: ContextFeatures) -> RuleResult:
    triggered = f.hour in NIGHT_HOURS and f.amount >= 50_000
    desc = f"Transaction nocturne ({f.hour:02d}h) d'un montant significatif ({f.amount:,.0f} XOF)"
    return RuleResult("NIGHT_ACTIVITY", desc, 15.0, triggered)


def _r_new_account_high_value(f: ContextFeatures) -> RuleResult:
    triggered = f.account_age_days < 7 and f.amount >= LARGE_AMOUNT_THRESHOLD
    desc = (
        f"Compte créé il y a {f.account_age_days:.1f} jours effectuant une "
        f"transaction de {f.amount:,.0f} XOF"
    )
    return RuleResult("NEW_ACCOUNT_HIGH_VALUE", desc, 30.0, triggered)


def _r_structuring(f: ContextFeatures) -> RuleResult:
    triggered = (
        f.tx_count_last_1h >= 4
        and f.sum_amount_last_1h + f.amount >= 1_000_000
        and f.amount < STRUCTURING_CEILING
    )
    desc = (
        f"Possible fractionnement : {f.tx_count_last_1h + 1} transactions cumulant "
        f"{f.sum_amount_last_1h + f.amount:,.0f} XOF en 1h, chacune sous le seuil de "
        f"{STRUCTURING_CEILING:,.0f} XOF"
    )
    return RuleResult("STRUCTURING_SUSPECTED", desc, 35.0, triggered)


def _r_fanout(f: ContextFeatures) -> RuleResult:
    triggered = f.distinct_receivers_last_1h >= 4
    desc = (
        f"{f.distinct_receivers_last_1h} bénéficiaires distincts en moins d'une heure "
        f"(schéma de distribution possible)"
    )
    return RuleResult("FANOUT_PATTERN", desc, 20.0, triggered)


RULES = [
    _r_amount_spike,
    _r_high_velocity,
    _r_unknown_receiver_high_amount,
    _r_night_activity,
    _r_new_account_high_value,
    _r_structuring,
    _r_fanout,
]


def evaluate_rules(features: ContextFeatures) -> list[RuleResult]:
    return [rule(features) for rule in RULES]


def aggregate_rule_score(results: list[RuleResult]) -> float:
    total = sum(r.weight for r in results if r.triggered)
    return min(total, 100.0)

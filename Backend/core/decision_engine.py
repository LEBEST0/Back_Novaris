"""Politique de décision : agrège règles + ML en un score final et une décision.

Cette logique est volontairement centralisée dans core/ (et non dans le module
transaction_monitoring) car elle est destinée à devenir, à terme, le point commun
utilisé par tous les modules spécialisés une fois branchés au Risk Orchestrator.
"""

from shared.config.settings import settings
from shared.utils.scoring import clamp, risk_level_from_score


def aggregate_final_score(rule_score: float, ml_score: float) -> float:
    weighted = settings.rule_weight * rule_score + settings.ml_weight * ml_score
    if rule_score >= settings.critical_rule_score_floor:
        # Garde-fou auditable : une règle critique ne doit jamais être diluée par un
        # score ML plus bas (le ML peut ne pas avoir vu ce pattern à l'entraînement).
        weighted = max(weighted, settings.critical_rule_score_floor)
    return clamp(weighted)


def compute_confidence(rule_score: float, ml_score: float) -> float:
    """Confiance = degré d'accord entre le signal règles et le signal ML.
    1.0 = les deux signaux pointent vers le même niveau de risque, 0.0 = désaccord total."""
    return round(clamp(1 - abs(rule_score - ml_score) / 100, 0, 1), 2)


def decide(final_score: float) -> tuple[str, str]:
    """Retourne (decision, risk_level) selon la matrice du document produit :
    0-29 ALLOW, 30-59 MONITOR, 60-79 REVIEW, 80-100 TEMPORARY_BLOCK."""
    risk_level = risk_level_from_score(final_score)
    if final_score >= settings.threshold_block:
        return "TEMPORARY_BLOCK", risk_level
    if final_score >= settings.threshold_review:
        return "REVIEW", risk_level
    if final_score >= settings.threshold_monitor:
        return "MONITOR", risk_level
    return "ALLOW", risk_level

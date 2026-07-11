"""Règles auditables du contrôle d'accès pré-transaction (device / intégrité / identité /
SIM / comportement). Même esprit que modules.transaction_monitoring.rules : chaque règle
est une fonction pure, déterministe, avec un code et un poids — pas de boîte noire."""

from dataclasses import dataclass, field


@dataclass
class AccessContext:
    is_new_device: bool
    cloned_device_id: bool
    device_integrity_failed: bool
    emulator_detected: bool
    root_detected: bool
    location_anomaly: bool
    impossible_travel: bool
    recent_sim_change: bool
    biometric_result: str | None  # "PASSED" | "FAILED" | None (pas encore tenté)
    liveness_result: str | None
    behaviour_anomaly: bool


@dataclass
class RuleResult:
    code: str
    description: str
    weight: float
    triggered: bool


def _r_new_device(ctx: AccessContext) -> RuleResult:
    return RuleResult(
        "NEW_DEVICE",
        "Connexion depuis un appareil jamais vu pour ce compte.",
        20.0,
        ctx.is_new_device,
    )


def _r_cloned_device_id(ctx: AccessContext) -> RuleResult:
    return RuleResult(
        "CLONED_DEVICE_ID",
        "L'identifiant d'appareil déclaré correspond à un appareil connu, mais l'empreinte "
        "applicative réelle diffère — signe probable d'usurpation d'identifiant.",
        45.0,
        ctx.cloned_device_id,
    )


def _r_integrity_failed(ctx: AccessContext) -> RuleResult:
    return RuleResult(
        "DEVICE_INTEGRITY_FAILED",
        "Le contrôle d'intégrité de l'appareil (Play Integrity simulé) a échoué.",
        40.0,
        ctx.device_integrity_failed,
    )


def _r_emulator(ctx: AccessContext) -> RuleResult:
    return RuleResult(
        "EMULATOR_DETECTED",
        "Émulateur détecté — accès probable depuis un environnement de test/fraude.",
        45.0,
        ctx.emulator_detected,
    )


def _r_root(ctx: AccessContext) -> RuleResult:
    return RuleResult(
        "ROOT_DETECTED",
        "Appareil rooté détecté — protections système contournées.",
        35.0,
        ctx.root_detected,
    )


def _r_location_anomaly(ctx: AccessContext) -> RuleResult:
    return RuleResult(
        "LOCATION_ANOMALY",
        "Connexion depuis une localisation inhabituelle pour ce client.",
        15.0,
        ctx.location_anomaly,
    )


def _r_impossible_travel(ctx: AccessContext) -> RuleResult:
    return RuleResult(
        "IMPOSSIBLE_TRAVEL",
        "Distance parcourue depuis la dernière session incompatible avec le temps écoulé.",
        35.0,
        ctx.impossible_travel,
    )


def _r_recent_sim_change(ctx: AccessContext) -> RuleResult:
    return RuleResult(
        "RECENT_SIM_CHANGE",
        "SIM ou eSIM changée récemment — fenêtre classique de prise de contrôle de compte.",
        30.0,
        ctx.recent_sim_change,
    )


def _r_biometric_failed(ctx: AccessContext) -> RuleResult:
    return RuleResult(
        "BIOMETRIC_FAILED",
        "La vérification biométrique (empreinte/Face ID) a échoué.",
        40.0,
        ctx.biometric_result == "FAILED",
    )


def _r_liveness_failed(ctx: AccessContext) -> RuleResult:
    return RuleResult(
        "LIVENESS_FAILED",
        "La vérification de vivacité (liveness) ou la pièce d'identité fournie n'a pas été validée.",
        45.0,
        ctx.liveness_result == "FAILED",
    )


def _r_behaviour_anomaly(ctx: AccessContext) -> RuleResult:
    return RuleResult(
        "BEHAVIOUR_ANOMALY",
        "Vitesse de saisie très différente du comportement habituel de ce client.",
        15.0,
        ctx.behaviour_anomaly,
    )


RULES = [
    _r_new_device,
    _r_cloned_device_id,
    _r_integrity_failed,
    _r_emulator,
    _r_root,
    _r_location_anomaly,
    _r_impossible_travel,
    _r_recent_sim_change,
    _r_biometric_failed,
    _r_liveness_failed,
    _r_behaviour_anomaly,
]


def evaluate_rules(ctx: AccessContext) -> list[RuleResult]:
    return [rule(ctx) for rule in RULES]


def evaluate_single_rules(ctx: AccessContext, codes: set[str]) -> list[RuleResult]:
    """Sous-ensemble de règles par code — utilisé par les endpoints de vérification
    isolée (/risk/device-check, /risk/identity-check, ...) qui n'évaluent qu'une partie
    du contexte."""
    return [result for result in evaluate_rules(ctx) if result.code in codes]


def aggregate_score(results: list[RuleResult]) -> float:
    return min(100.0, sum(r.weight for r in results if r.triggered))

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from backend.app.modules.behavioural_biometrics.schemas import BehaviouralSampleInput


@dataclass(slots=True)
class BehaviouralRiskEvaluation:
    score: int
    risk_level: str
    decision: str
    reasons: list[str]
    evidence: dict[str, Any]
    adapter_mode: str = "RULE_BASED"
    profile_samples: int = 0


def _risk_level(score: int) -> str:
    if score <= 29:
        return "LOW"
    if score <= 59:
        return "MEDIUM"
    if score <= 79:
        return "HIGH"
    return "CRITICAL"


def _decision(risk_level: str) -> str:
    return {
        "LOW": "ALLOW",
        "MEDIUM": "REQUIRE_OTP",
        "HIGH": "REQUIRE_STEP_UP",
        "CRITICAL": "DENY_OR_HOLD_ACTION",
    }[risk_level]


def _metric(profile: dict[str, Any], field: str) -> dict[str, float] | None:
    metrics = profile.get("metrics", {}) if profile else {}
    return metrics.get(field)


def _deviation_flag(
    value: float | None,
    metric: dict[str, float] | None,
    *,
    ratio_threshold: float = 0.35,
    std_factor: float = 2.0,
    min_abs: float = 0.0,
) -> bool:
    if value is None or not metric:
        return False
    mean = metric["mean"]
    std = metric["std"]
    tolerance = max(abs(mean) * ratio_threshold, std * std_factor, min_abs)
    return abs(value - mean) > tolerance


def _evidence_payload(current_sample: BehaviouralSampleInput, profile: Any) -> dict[str, Any]:
    profile_baseline = getattr(profile, "baseline", None) if profile is not None else None
    samples_count = len(getattr(profile, "samples", []) or []) if profile is not None else 0
    return {
        "current_sample": current_sample.model_dump(mode="json"),
        "profile": None
        if profile is None
        else {
            "user_id": profile.user_id,
            "samples_count": samples_count,
            "baseline": profile_baseline,
        },
    }


def evaluate_behavioural_risk(current_sample: BehaviouralSampleInput, profile: Any) -> dict[str, Any]:
    profile_baseline = getattr(profile, "baseline", None) if profile is not None else None
    samples_count = len(getattr(profile, "samples", []) or []) if profile is not None else 0
    evidence = _evidence_payload(current_sample, profile)

    if profile is None or samples_count == 0:
        return asdict(
            BehaviouralRiskEvaluation(
                score=50,
                risk_level="MEDIUM",
                decision="REQUIRE_OTP",
                reasons=["Profil comportemental insuffisant"],
                evidence={**evidence, "reason": "no_profile"},
                profile_samples=0,
            )
        )

    score = 0
    reasons: list[str] = []

    if samples_count < 3:
        score += 20
        reasons.append("Peu d'echantillons comportementaux")

    key_interval = current_sample.avg_key_interval_ms
    touch_duration = current_sample.avg_touch_duration_ms
    typing_speed = current_sample.typing_speed_cps
    error_count = current_sample.error_count
    correction_count = current_sample.correction_count
    hesitation = current_sample.hesitation_time_ms
    touch_precision = current_sample.touch_precision_score
    session_duration = current_sample.session_duration_ms

    key_metric = _metric(profile_baseline or {}, "avg_key_interval_ms")
    touch_metric = _metric(profile_baseline or {}, "avg_touch_duration_ms")
    speed_metric = _metric(profile_baseline or {}, "typing_speed_cps")
    error_metric = _metric(profile_baseline or {}, "error_count")
    correction_metric = _metric(profile_baseline or {}, "correction_count")
    hesitation_metric = _metric(profile_baseline or {}, "hesitation_time_ms")
    precision_metric = _metric(profile_baseline or {}, "touch_precision_score")
    session_metric = _metric(profile_baseline or {}, "session_duration_ms")
    key_std_metric = _metric(profile_baseline or {}, "avg_key_interval_ms")
    touch_std_metric = _metric(profile_baseline or {}, "avg_touch_duration_ms")

    very_different_key_interval = _deviation_flag(key_interval, key_metric, ratio_threshold=0.30, std_factor=1.5, min_abs=25)
    very_different_touch_duration = _deviation_flag(touch_duration, touch_metric, ratio_threshold=0.35, std_factor=1.5, min_abs=20)
    very_different_typing_speed = _deviation_flag(typing_speed, speed_metric, ratio_threshold=0.30, std_factor=1.5, min_abs=0.4)

    if very_different_key_interval:
        score += 25
        reasons.append("Intervalle de frappe tres different de l'habitude")
    if very_different_touch_duration:
        score += 15
        reasons.append("Duree moyenne de touch differente")
    if very_different_typing_speed:
        score += 20
        reasons.append("Vitesse de frappe tres differente")
    if error_count is not None and error_metric and error_count > error_metric["mean"] + max(error_metric["std"], 1.0):
        score += 15
        reasons.append("Nombre d'erreurs superieur a l'habitude")
    if correction_count is not None and correction_metric and correction_count > correction_metric["mean"] + max(correction_metric["std"], 1.0):
        score += 10
        reasons.append("Nombre de corrections superieur a l'habitude")
    if hesitation is not None and hesitation_metric and hesitation > hesitation_metric["mean"] + max(hesitation_metric["std"] * 2, hesitation_metric["mean"] * 0.5, 100):
        score += 15
        reasons.append("Temps d'hesitation tres eleve")
    if touch_precision is not None and precision_metric and touch_precision < precision_metric["mean"] - max(precision_metric["std"] * 2, abs(precision_metric["mean"]) * 0.2, 0.1):
        score += 15
        reasons.append("Precision tactile faible")
    if session_duration is not None and session_metric:
        short_limit = session_metric["mean"] * 0.5
        long_limit = session_metric["mean"] * 1.8
        if session_duration < short_limit or session_duration > long_limit:
            score += 10
            reasons.append("Duree de session anormale")
    if (
        key_std_metric
        and touch_std_metric
        and speed_metric
        and key_std_metric["std"] < 20
        and touch_std_metric["std"] < 20
        and typing_speed is not None
        and typing_speed > speed_metric["mean"] * 1.2
    ):
        score += 20
        reasons.append("Rythme trop mecanique")

    score = min(score, 100)
    risk_level = _risk_level(score)
    decision = _decision(risk_level)

    evidence.update(
        {
            "baseline": profile_baseline,
            "samples_count": samples_count,
            "score_components": {
                "few_samples": samples_count < 3,
                "very_different_key_interval": very_different_key_interval,
                "very_different_touch_duration": very_different_touch_duration,
                "very_different_typing_speed": very_different_typing_speed,
            },
        }
    )

    return asdict(
        BehaviouralRiskEvaluation(
            score=score,
            risk_level=risk_level,
            decision=decision,
            reasons=reasons,
            evidence=evidence,
            profile_samples=samples_count,
        )
    )

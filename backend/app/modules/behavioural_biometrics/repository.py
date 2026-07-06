from __future__ import annotations

from statistics import fmean, pstdev
from threading import RLock
from typing import Any

from backend.app.modules.behavioural_biometrics.models import BehaviouralProfileRecord, BehaviouralSampleRecord, utcnow
from backend.app.modules.behavioural_biometrics.schemas import BehaviouralSampleInput

_LOCK = RLock()
_PROFILES: dict[str, BehaviouralProfileRecord] = {}

_NUMERIC_FIELDS = (
    "avg_key_interval_ms",
    "avg_touch_duration_ms",
    "typing_speed_cps",
    "tap_pressure_avg",
    "tap_pressure_std",
    "error_count",
    "correction_count",
    "hesitation_time_ms",
    "swipe_speed_avg",
    "touch_precision_score",
    "device_orientation_changes",
    "session_duration_ms",
)


def reset_repository() -> None:
    with _LOCK:
        _PROFILES.clear()


def _to_record(sample: BehaviouralSampleInput) -> BehaviouralSampleRecord:
    return BehaviouralSampleRecord(**sample.model_dump(mode="json"))


def _safe_std(values: list[float]) -> float:
    return pstdev(values) if len(values) > 1 else 0.0


def _compute_baseline(samples: list[BehaviouralSampleRecord]) -> dict[str, Any]:
    baseline: dict[str, Any] = {"samples_count": len(samples), "metrics": {}}
    for field in _NUMERIC_FIELDS:
        values = [float(getattr(sample, field)) for sample in samples if getattr(sample, field) is not None]
        if not values:
            continue
        baseline["metrics"][field] = {
            "mean": round(fmean(values), 4),
            "std": round(_safe_std(values), 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
        }
    return baseline


def enroll_sample(sample: BehaviouralSampleInput) -> BehaviouralProfileRecord:
    record = _to_record(sample)
    with _LOCK:
        profile = _PROFILES.get(sample.user_id)
        if profile is None:
            profile = BehaviouralProfileRecord(user_id=sample.user_id)
            _PROFILES[sample.user_id] = profile
        profile.samples.append(record)
        profile.baseline = _compute_baseline(profile.samples)
        profile.updated_at = utcnow()
        if len(profile.samples) == 1:
            profile.created_at = profile.updated_at
        return profile


def get_user_profile(user_id: str) -> BehaviouralProfileRecord | None:
    with _LOCK:
        return _PROFILES.get(user_id)


def get_user_samples(user_id: str) -> list[BehaviouralSampleRecord]:
    with _LOCK:
        profile = _PROFILES.get(user_id)
        return list(profile.samples) if profile else []


def count_user_samples(user_id: str) -> int:
    with _LOCK:
        profile = _PROFILES.get(user_id)
        return len(profile.samples) if profile else 0

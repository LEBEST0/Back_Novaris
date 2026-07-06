from __future__ import annotations

from statistics import fmean, pstdev
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from backend.app.modules.behavioural_biometrics.models import BehaviouralProfile, BehaviouralSample, utcnow
from backend.app.modules.behavioural_biometrics.schemas import BehaviouralSampleInput

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


def _safe_std(values: list[float]) -> float:
    return pstdev(values) if len(values) > 1 else 0.0


def _compute_baseline(samples: list[BehaviouralSample]) -> dict[str, Any]:
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


def _to_sample(sample: BehaviouralSampleInput) -> dict[str, Any]:
    payload = sample.model_dump(mode="json")
    payload.pop("user_id", None)
    payload.pop("session_id", None)
    return payload


def _load_profile(db: Session, user_id: str) -> BehaviouralProfile | None:
    stmt = (
        select(BehaviouralProfile)
        .options(selectinload(BehaviouralProfile.samples))
        .where(BehaviouralProfile.user_id == user_id)
    )
    return db.scalar(stmt)


def reset_repository(db: Session) -> None:
    db.execute(delete(BehaviouralSample))
    db.execute(delete(BehaviouralProfile))
    db.commit()


def enroll_sample(db: Session, sample: BehaviouralSampleInput) -> BehaviouralProfile:
    profile = _load_profile(db, sample.user_id)
    now = utcnow()
    if profile is None:
        profile = BehaviouralProfile(
            user_id=sample.user_id,
            samples_count=0,
            baseline_data={},
            created_at=now,
            updated_at=now,
        )
        db.add(profile)
        db.flush()

    sample_row = BehaviouralSample(
        profile=profile,
        user_id=sample.user_id,
        session_id=sample.session_id,
        **_to_sample(sample),
    )
    db.add(sample_row)
    db.flush()

    samples = get_user_samples(db, sample.user_id)
    profile.samples_count = len(samples)
    profile.baseline = _compute_baseline(samples)
    profile.updated_at = now
    if profile.created_at is None:
        profile.created_at = now

    db.commit()
    db.refresh(profile)
    return profile


def get_user_profile(db: Session, user_id: str) -> BehaviouralProfile | None:
    return _load_profile(db, user_id)


def get_user_samples(db: Session, user_id: str) -> list[BehaviouralSample]:
    stmt = select(BehaviouralSample).where(BehaviouralSample.user_id == user_id).order_by(BehaviouralSample.created_at.asc(), BehaviouralSample.id.asc())
    return list(db.scalars(stmt).all())


def count_user_samples(db: Session, user_id: str) -> int:
    profile = _load_profile(db, user_id)
    return profile.samples_count if profile else 0

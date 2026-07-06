from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class BehaviouralSampleRecord:
    user_id: str
    session_id: str
    action_type: str
    avg_key_interval_ms: float | None
    avg_touch_duration_ms: float | None
    typing_speed_cps: float | None
    tap_pressure_avg: float | None
    tap_pressure_std: float | None
    error_count: int | None
    correction_count: int | None
    hesitation_time_ms: float | None
    swipe_speed_avg: float | None
    touch_precision_score: float | None
    device_orientation_changes: int | None
    session_duration_ms: float | None
    platform: str | None
    payload_version: str | None
    created_at: datetime = field(default_factory=utcnow)


@dataclass(slots=True)
class BehaviouralProfileRecord:
    user_id: str
    samples: list[BehaviouralSampleRecord] = field(default_factory=list)
    baseline: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


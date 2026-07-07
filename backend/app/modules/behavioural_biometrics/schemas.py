from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class BehaviouralActionType(str, Enum):
    LOGIN = "LOGIN"
    PIN_ENTRY = "PIN_ENTRY"
    TRANSACTION_CONFIRMATION = "TRANSACTION_CONFIRMATION"
    PASSWORD_CHANGE = "PASSWORD_CHANGE"
    BENEFICIARY_ADD = "BENEFICIARY_ADD"


class BehaviouralSampleInput(BaseModel):
    user_id: str
    session_id: str
    action_type: BehaviouralActionType
    request_id: str
    timestamp: datetime
    nonce: str
    sdk_version: str
    payload_version: Literal["v1"]
    platform: Literal["ANDROID", "IOS", "WEB_MOCK"]
    avg_key_interval_ms: float | None = None
    avg_touch_duration_ms: float | None = None
    typing_speed_cps: float | None = None
    tap_pressure_avg: float | None = None
    tap_pressure_std: float | None = None
    error_count: int | None = None
    correction_count: int | None = None
    hesitation_time_ms: float | None = None
    swipe_speed_avg: float | None = None
    touch_precision_score: float | None = None
    device_orientation_changes: int | None = None
    session_duration_ms: float | None = None

    model_config = ConfigDict(extra="ignore")


class BehaviouralEnrollRequest(BehaviouralSampleInput):
    pass


class BehaviouralRiskResponse(BaseModel):
    module_name: str
    user_id: str
    session_id: str
    score: int = Field(ge=0, le=100)
    risk_level: str
    decision: str
    reasons: list[str]
    evidence: dict[str, Any]
    profile_samples: int
    adapter_mode: str


class BehaviouralProfileResponse(BaseModel):
    user_id: str
    samples_count: int
    baseline: dict[str, Any]
    created_at: datetime
    updated_at: datetime

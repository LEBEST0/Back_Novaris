from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DevicePlatform(str, Enum):
    ANDROID = "ANDROID"
    IOS = "IOS"
    WEB_MOCK = "WEB_MOCK"


class DeviceMetadataInput(BaseModel):
    user_id: str
    device_id: str
    brand: str
    model: str
    os_name: str
    os_version: str
    app_version: str | None = None
    is_rooted: bool
    is_emulator: bool
    is_vpn: bool
    is_proxy: bool
    ip_address: str | None = None
    country: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    language: str | None = None

    model_config = ConfigDict(extra="ignore")


class DeviceEnrollRequest(BaseModel):
    user_id: str
    device: DeviceMetadataInput


class DeviceAnalyzeRequest(DeviceMetadataInput):
    request_id: str
    timestamp: datetime
    nonce: str
    sdk_version: str | None = None
    payload_version: Literal["v1"] = "v1"
    platform: DevicePlatform


class DeviceRiskResponse(BaseModel):
    module_name: str
    user_id: str
    device_id: str
    score: int = Field(ge=0, le=100)
    confidence_score: int = Field(ge=0, le=100)
    risk_level: str
    decision: str
    reasons: list[str]
    evidence: dict[str, Any]
    adapter_mode: str


class DeviceEnrollResponse(BaseModel):
    status: str
    user_id: str
    device_id: str
    device_hash: str
    device_status: str

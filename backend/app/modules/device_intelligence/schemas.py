from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class DeviceRiskResponse(BaseModel):
    module_name: str
    user_id: str
    device_id: str
    score: int = Field(ge=0, le=100)
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


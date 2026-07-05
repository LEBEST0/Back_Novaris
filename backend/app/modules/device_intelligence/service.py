from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.modules.device_intelligence import repository
from backend.app.modules.device_intelligence.ml import DeviceIntelligenceMLPredictor
from backend.app.modules.device_intelligence.models import DeviceStatus
from backend.app.modules.device_intelligence.rules import evaluate_device_risk
from backend.app.modules.device_intelligence.schemas import (
    DeviceEnrollRequest,
    DeviceAnalyzeRequest,
    DeviceEnrollResponse,
    DeviceMetadataInput,
    DeviceRiskResponse,
)


class DeviceIntelligenceService:
    MAX_TIMESTAMP_DRIFT_SECONDS = 300

    def __init__(self, db: Session, predictor: DeviceIntelligenceMLPredictor | None = None) -> None:
        self.db = db
        self.predictor = predictor or DeviceIntelligenceMLPredictor()

    @staticmethod
    def build_device_hash(device: DeviceMetadataInput) -> str:
        raw = "|".join(
            [
                device.brand,
                device.model,
                device.os_name,
                device.os_version,
                device.user_id,
                device.device_id,
                device.language or "",
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def enroll(self, payload: DeviceEnrollRequest) -> DeviceEnrollResponse:
        device = payload.device.model_copy(update={"user_id": payload.user_id})
        device_hash = self.build_device_hash(device)
        record = repository.enroll_device(self.db, device, device_hash, DeviceStatus.TRUSTED.value)
        return DeviceEnrollResponse(
            status="ENROLLED",
            user_id=record.user_id,
            device_id=record.device_id,
            device_hash=record.device_hash,
            device_status=record.status,
        )

    @staticmethod
    def _expected_client_key() -> str:
        return os.getenv("NOVARIS_DEVICE_CLIENT_KEY", "novaris-device-client-key")

    @staticmethod
    def _validate_timestamp(timestamp: datetime) -> None:
        now = datetime.now(timezone.utc)
        current = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
        delta = abs((now - current).total_seconds())
        if delta > DeviceIntelligenceService.MAX_TIMESTAMP_DRIFT_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="timestamp outside allowed 5 minute window",
            )

    def _validate_client_key(self, client_key: str | None) -> None:
        if not client_key or client_key != self._expected_client_key():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="invalid or missing X-Novaris-Client-Key",
            )

    def analyze(self, payload: DeviceAnalyzeRequest, client_key: str | None) -> DeviceRiskResponse:
        self._validate_client_key(client_key)
        self._validate_timestamp(payload.timestamp)

        if not repository.register_request_nonce(self.db, payload):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="nonce already used",
            )

        device_hash = self.build_device_hash(payload)
        history_devices = repository.get_user_devices(self.db, payload.user_id)
        latest_trusted_device = repository.get_latest_trusted_device(self.db, payload.user_id)

        evaluation = evaluate_device_risk(
            payload,
            {
                "history_devices": history_devices,
                "latest_trusted_device": latest_trusted_device,
            },
        )

        if evaluation["decision"] == "ALLOW_PIN":
            repository.enroll_device(self.db, payload, device_hash, DeviceStatus.TRUSTED.value)
            repository.update_last_used(self.db, payload.user_id, payload.device_id)
        elif evaluation["decision"] == "REQUIRE_OTP":
            repository.mark_device_suspicious(self.db, payload, device_hash)
        elif evaluation["decision"] == "REQUIRE_STEP_UP":
            repository.mark_device_suspicious(self.db, payload, device_hash)
        else:
            repository.mark_device_blocked(self.db, payload, device_hash)

        return DeviceRiskResponse(
            module_name="device_intelligence",
            user_id=payload.user_id,
            device_id=payload.device_id,
            score=evaluation["score"],
            risk_level=evaluation["risk_level"],
            decision=evaluation["decision"],
            reasons=evaluation["reasons"],
            evidence=evaluation["evidence"],
            adapter_mode=evaluation["adapter_mode"],
        )

    def list_devices(self, user_id: str) -> list[dict[str, Any]]:
        records = repository.get_user_devices(self.db, user_id)
        return [
            {
                "id": record.id,
                "user_id": record.user_id,
                "device_id": record.device_id,
                "device_hash": record.device_hash,
                "brand": record.brand,
                "model": record.model,
                "os_name": record.os_name,
                "os_version": record.os_version,
                "ip_address": record.ip_address,
                "country": record.country,
                "city": record.city,
                "status": record.status,
                "first_seen_at": record.first_seen_at,
                "last_used_at": record.last_used_at,
                "created_at": record.created_at,
            }
            for record in records
        ]

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.modules.behavioural_biometrics import repository
from backend.app.modules.behavioural_biometrics.ml import BehaviouralBiometricsMLPredictor
from backend.app.modules.behavioural_biometrics.models import BehaviouralProfile
from backend.app.modules.behavioural_biometrics.rules import evaluate_behavioural_risk
from backend.app.modules.behavioural_biometrics.schemas import (
    BehaviouralEnrollRequest,
    BehaviouralProfileResponse,
    BehaviouralRiskResponse,
    BehaviouralSampleInput,
)
from backend.app.shared.config.constants import SECURITY_TIMESTAMP_WINDOW_SECONDS


class BehaviouralBiometricsService:
    def __init__(self, predictor: BehaviouralBiometricsMLPredictor | None = None) -> None:
        self.predictor = predictor or BehaviouralBiometricsMLPredictor()

    @staticmethod
    def _profile_to_response(profile: BehaviouralProfile) -> BehaviouralProfileResponse:
        return BehaviouralProfileResponse(
            user_id=profile.user_id,
            samples_count=profile.samples_count,
            baseline=profile.baseline,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    @staticmethod
    def _normalize_timestamp(timestamp: datetime) -> datetime:
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc)

    def _validate_security_and_register_nonce(self, db: Session, payload: BehaviouralSampleInput, *, endpoint: str) -> None:
        request_timestamp = self._normalize_timestamp(payload.timestamp)
        now = datetime.now(timezone.utc)
        if abs((now - request_timestamp).total_seconds()) > SECURITY_TIMESTAMP_WINDOW_SECONDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="timestamp outside allowed window")

        if repository.is_nonce_used(db, payload.nonce):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="nonce already used")

        if not repository.register_nonce(
            db,
            nonce=payload.nonce,
            request_id=payload.request_id,
            user_id=payload.user_id,
            endpoint=endpoint,
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="nonce already used")

    @staticmethod
    def _compute_confidence_score(
        *,
        signature_valid: bool,
        client_key_valid: bool,
        timestamp_fresh: bool,
        nonce_unused: bool,
        payload_supported: bool,
    ) -> int:
        score = 0
        if signature_valid:
            score += 40
        if client_key_valid:
            score += 20
        if timestamp_fresh:
            score += 15
        if nonce_unused:
            score += 15
        if payload_supported:
            score += 10
        return min(score, 100)

    def enroll_behavioural_sample(self, db: Session, payload: BehaviouralEnrollRequest) -> BehaviouralProfileResponse:
        self._validate_security_and_register_nonce(db, payload, endpoint="enroll")
        profile = repository.enroll_sample(db, payload)
        return self._profile_to_response(profile)

    def analyze_behavioural_sample(self, db: Session, payload: BehaviouralSampleInput) -> BehaviouralRiskResponse:
        self._validate_security_and_register_nonce(db, payload, endpoint="analyze")
        profile = repository.get_user_profile(db, payload.user_id)
        evaluation = evaluate_behavioural_risk(payload, profile)
        return BehaviouralRiskResponse(
            module_name="behavioural_biometrics",
            user_id=payload.user_id,
            session_id=payload.session_id,
            score=evaluation["score"],
            confidence_score=self._compute_confidence_score(
                signature_valid=True,
                client_key_valid=True,
                timestamp_fresh=True,
                nonce_unused=True,
                payload_supported=True,
            ),
            risk_level=evaluation["risk_level"],
            decision=evaluation["decision"],
            reasons=evaluation["reasons"],
            evidence=evaluation["evidence"],
            profile_samples=evaluation["profile_samples"],
            adapter_mode=evaluation["adapter_mode"],
        )

    def get_behavioural_profile(self, db: Session, user_id: str) -> BehaviouralProfileResponse:
        profile = repository.get_user_profile(db, user_id)
        if profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="behavioural profile not found")
        return self._profile_to_response(profile)

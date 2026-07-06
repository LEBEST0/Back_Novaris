from __future__ import annotations

from fastapi import HTTPException, status

from backend.app.modules.behavioural_biometrics import repository
from backend.app.modules.behavioural_biometrics.ml import BehaviouralBiometricsMLPredictor
from backend.app.modules.behavioural_biometrics.models import BehaviouralProfileRecord
from backend.app.modules.behavioural_biometrics.rules import evaluate_behavioural_risk
from backend.app.modules.behavioural_biometrics.schemas import (
    BehaviouralEnrollRequest,
    BehaviouralProfileResponse,
    BehaviouralRiskResponse,
    BehaviouralSampleInput,
)


class BehaviouralBiometricsService:
    def __init__(self, predictor: BehaviouralBiometricsMLPredictor | None = None) -> None:
        self.predictor = predictor or BehaviouralBiometricsMLPredictor()

    @staticmethod
    def _profile_to_response(profile: BehaviouralProfileRecord) -> BehaviouralProfileResponse:
        return BehaviouralProfileResponse(
            user_id=profile.user_id,
            samples_count=len(profile.samples),
            baseline=profile.baseline,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    def enroll_behavioural_sample(self, payload: BehaviouralEnrollRequest) -> BehaviouralProfileResponse:
        repository.enroll_sample(payload)
        profile = repository.get_user_profile(payload.user_id)
        if profile is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="profile enrollment failed")
        return self._profile_to_response(profile)

    def analyze_behavioural_sample(self, payload: BehaviouralSampleInput) -> BehaviouralRiskResponse:
        profile = repository.get_user_profile(payload.user_id)
        evaluation = evaluate_behavioural_risk(payload, profile)
        return BehaviouralRiskResponse(
            module_name="behavioural_biometrics",
            user_id=payload.user_id,
            session_id=payload.session_id,
            score=evaluation["score"],
            risk_level=evaluation["risk_level"],
            decision=evaluation["decision"],
            reasons=evaluation["reasons"],
            evidence=evaluation["evidence"],
            profile_samples=evaluation["profile_samples"],
            adapter_mode=evaluation["adapter_mode"],
        )

    def get_behavioural_profile(self, user_id: str) -> BehaviouralProfileResponse:
        profile = repository.get_user_profile(user_id)
        if profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="behavioural profile not found")
        return self._profile_to_response(profile)


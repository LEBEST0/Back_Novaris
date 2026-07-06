from fastapi import APIRouter

from backend.app.modules.behavioural_biometrics.schemas import (
    BehaviouralEnrollRequest,
    BehaviouralProfileResponse,
    BehaviouralRiskResponse,
    BehaviouralSampleInput,
)
from backend.app.modules.behavioural_biometrics.service import BehaviouralBiometricsService

router = APIRouter(prefix="/behavioural-biometrics", tags=["behavioural-biometrics"])
service = BehaviouralBiometricsService()


@router.post("/enroll", response_model=BehaviouralProfileResponse)
def enroll_behavioural_sample(payload: BehaviouralEnrollRequest) -> BehaviouralProfileResponse:
    return service.enroll_behavioural_sample(payload)


@router.post("/analyze", response_model=BehaviouralRiskResponse)
def analyze_behavioural_sample(payload: BehaviouralSampleInput) -> BehaviouralRiskResponse:
    return service.analyze_behavioural_sample(payload)


@router.get("/users/{user_id}/profile", response_model=BehaviouralProfileResponse)
def get_behavioural_profile(user_id: str) -> BehaviouralProfileResponse:
    return service.get_behavioural_profile(user_id)


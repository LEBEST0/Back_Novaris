from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
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
def enroll_behavioural_sample(
    payload: BehaviouralEnrollRequest,
    db: Session = Depends(get_db),
) -> BehaviouralProfileResponse:
    return service.enroll_behavioural_sample(db, payload)


@router.post("/analyze", response_model=BehaviouralRiskResponse)
def analyze_behavioural_sample(
    payload: BehaviouralSampleInput,
    db: Session = Depends(get_db),
) -> BehaviouralRiskResponse:
    return service.analyze_behavioural_sample(db, payload)


@router.get("/users/{user_id}/profile", response_model=BehaviouralProfileResponse)
def get_behavioural_profile(
    user_id: str,
    db: Session = Depends(get_db),
) -> BehaviouralProfileResponse:
    return service.get_behavioural_profile(db, user_id)


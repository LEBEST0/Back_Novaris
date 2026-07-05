from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.modules.device_intelligence.schemas import (
    DeviceAnalyzeRequest,
    DeviceEnrollRequest,
    DeviceMetadataInput,
    DeviceRiskResponse,
)
from backend.app.modules.device_intelligence.service import DeviceIntelligenceService

router = APIRouter(prefix="/device-intelligence", tags=["device-intelligence"])


@router.post("/enroll")
def enroll_device(payload: DeviceEnrollRequest, db: Session = Depends(get_db)):
    service = DeviceIntelligenceService(db)
    return service.enroll(payload)


@router.post("/analyze", response_model=DeviceRiskResponse)
def analyze_device(
    payload: DeviceAnalyzeRequest,
    db: Session = Depends(get_db),
    x_novaris_client_key: str | None = Header(default=None, alias="X-Novaris-Client-Key"),
) -> DeviceRiskResponse:
    service = DeviceIntelligenceService(db)
    return service.analyze(payload, x_novaris_client_key)


@router.get("/users/{user_id}/devices")
def list_user_devices(user_id: str, db: Session = Depends(get_db)):
    service = DeviceIntelligenceService(db)
    return service.list_devices(user_id)

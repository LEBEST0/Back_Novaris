from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.modules.device_intelligence.schemas import DeviceEnrollRequest, DeviceMetadataInput, DeviceRiskResponse
from backend.app.modules.device_intelligence.service import DeviceIntelligenceService

router = APIRouter(prefix="/device-intelligence", tags=["device-intelligence"])


@router.post("/enroll")
def enroll_device(payload: DeviceEnrollRequest, db: Session = Depends(get_db)):
    service = DeviceIntelligenceService(db)
    return service.enroll(payload)


@router.post("/analyze", response_model=DeviceRiskResponse)
def analyze_device(payload: DeviceMetadataInput, db: Session = Depends(get_db)) -> DeviceRiskResponse:
    service = DeviceIntelligenceService(db)
    return service.analyze(payload)


@router.get("/users/{user_id}/devices")
def list_user_devices(user_id: str, db: Session = Depends(get_db)):
    service = DeviceIntelligenceService(db)
    return service.list_devices(user_id)


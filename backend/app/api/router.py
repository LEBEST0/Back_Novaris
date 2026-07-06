from fastapi import APIRouter

from backend.app.modules.behavioural_biometrics.api import router as behavioural_biometrics_router
from backend.app.modules.device_intelligence.api import router as device_intelligence_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(behavioural_biometrics_router)
api_router.include_router(device_intelligence_router)

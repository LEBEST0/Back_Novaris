from fastapi import APIRouter

from modules.transaction_monitoring.api import router as transaction_monitoring_router

api_router = APIRouter()
api_router.include_router(transaction_monitoring_router)

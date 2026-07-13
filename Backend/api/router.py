from fastapi import APIRouter

from modules.transaction_monitoring.api import customers_router, dashboard_router
from modules.transaction_monitoring.api import router as transaction_monitoring_router
from modules.wallet_access.api import access_router, wallet_router

api_router = APIRouter()
api_router.include_router(transaction_monitoring_router)
api_router.include_router(dashboard_router)
api_router.include_router(customers_router)
api_router.include_router(access_router)
api_router.include_router(wallet_router)

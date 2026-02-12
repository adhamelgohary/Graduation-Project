from fastapi import APIRouter
from .user_alerts import user_alerts_router

api_router = APIRouter(prefix="/api")

api_router.include_router(user_alerts_router, prefix="/alerts")

"""API 버전 1 라우터 집계."""

from fastapi import APIRouter

from app.api.v1 import alerts, auth, control, dashboard, energy, kepco, reports, sensors, weather, ws
from app.core.config import settings

api_v1_router = APIRouter(prefix=settings.API_V1_PREFIX)

api_v1_router.include_router(auth.router)
api_v1_router.include_router(sensors.router)
api_v1_router.include_router(dashboard.router)
api_v1_router.include_router(alerts.router)
api_v1_router.include_router(control.router)
api_v1_router.include_router(reports.router)
api_v1_router.include_router(ws.router)
api_v1_router.include_router(energy.router, prefix="/energy", tags=["energy"])
api_v1_router.include_router(weather.router, prefix="/weather", tags=["weather"])
api_v1_router.include_router(kepco.router, prefix="/kepco", tags=["kepco"])

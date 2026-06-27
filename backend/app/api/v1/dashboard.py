"""대시보드 API — 건물별 실시간 상태."""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import settings
from app.core.constants import DeviceType, SensorType
from app.core.deps import DbSession
from app.repositories.alert_repository import AlertRepository
from app.repositories.device_repository import DeviceRepository
from app.repositories.energy_repository import EnergyRepository
from app.repositories.sensor_repository import SensorRepository
from app.schemas.response import success_response
from app.services.forecast_service import ForecastService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/{building_id}")
async def get_dashboard(session: DbSession, building_id: str) -> dict:
    """
    GET /api/v1/dashboard/{building_id}

    건물별 실시간 피크쉐이빙 대시보드 데이터.
    """
    sensor_repo = SensorRepository(session)
    device_repo = DeviceRepository(session)
    alert_repo = AlertRepository(session)
    energy_repo = EnergyRepository(session)
    forecast_svc = ForecastService(session)

    grid = await sensor_repo.get_latest_by_building(
        building_id, SensorType.GRID_CURRENT.value, DeviceType.GRID_METER.value
    )
    ess = await sensor_repo.get_latest_by_building(
        building_id, SensorType.ESS_SOC.value, DeviceType.ESS.value
    )

    chargers = await device_repo.list_by_building(
        building_id, DeviceType.CHARGER.value
    )
    charger_data = []
    for charger in chargers:
        latest = await sensor_repo.get_latest(
            charger.device_id, SensorType.CHARGER_CURRENT.value
        )
        charger_data.append(
            {
                "device_id": charger.device_id,
                "current": latest.value if latest else 0.0,
                "status": charger.status,
            }
        )

    today = await energy_repo.get_by_date(building_id, datetime.now(timezone.utc).date())
    month_saved = await energy_repo.get_month_total(building_id)
    try:
        forecast = await forecast_svc.get_next_hour_summary(building_id)
    except Exception:
        forecast = []
    peak_active = await alert_repo.has_active_peak(building_id)

    data = {
        "grid_current": grid.value if grid else 0.0,
        "ess_soc": ess.value if ess else 0.0,
        "peak_active": peak_active,
        "peak_threshold": settings.PEAK_THRESHOLD_A,
        "chargers": charger_data,
        "forecast": forecast,
        "today_saved_won": today.saved_won if today else 0.0,
        "month_saved_won": month_saved,
        "co2_reduced_kg": today.co2_reduced_kg if today else 0.0,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    return success_response(data)

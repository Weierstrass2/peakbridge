"""통합 상태 수집 API."""

from datetime import datetime

from fastapi import APIRouter

from app.schemas.response import success_response

router = APIRouter()


@router.get("/{building_id}")
async def get_state(building_id: str) -> dict:
    """GET /api/v1/state/{building_id}."""
    now = datetime.now()
    return success_response(
        {
            "status": "not_implemented",
            "building_id": building_id,
            "grid_current": 0.0,
            "ess_soc": 50.0,
            "ess_available": True,
            "current_temp": 25.0,
            "tomorrow_max_temp": 28.0,
            "smp_price": 100.0,
            "tariff_rate": 84.5,
            "hour": now.hour,
            "weekday": now.weekday(),
            "season": "summer",
            "is_holiday": False,
            "transformer_load": 0.0,
            "charger_count": 0,
            "lag_1h": 0.0,
            "rolling_mean_3h": 0.0,
        }
    )

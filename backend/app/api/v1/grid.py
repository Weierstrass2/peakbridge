"""배전망 시뮬레이션 API — pandapower 기반 변압기 부하율 분석."""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.constants import DeviceType, SensorType
from app.core.deps import DbSession
from app.ml.grid_simulator import grid_simulator
from app.repositories.device_repository import DeviceRepository
from app.repositories.sensor_repository import SensorRepository
from app.schemas.response import success_response

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/grid", tags=["grid"])


class GridSimulateRequest(BaseModel):
    """수동 시뮬레이션 요청."""

    grid_current: float = Field(ge=0, le=1000, description="그리드 전류 (A)")
    ess_discharge_kw: float = Field(default=5.0, ge=0, le=100, description="ESS 유닛당 방전 (kW)")
    ev_count: int = Field(default=1, ge=0, le=100, description="EV 충전 대수")
    transformer_kva: float = Field(default=300.0, gt=0, le=10000, description="변압기 정격 (kVA)")


@router.post("/simulate")
async def simulate_grid(body: GridSimulateRequest) -> dict:
    """
    POST /api/v1/grid/simulate

    입력값 기반 변압기 부하율 시뮬레이션 (PeakBridge 적용 전/후).
    """
    try:
        result = grid_simulator.simulate(
            grid_current=body.grid_current,
            ess_discharge_kw=body.ess_discharge_kw,
            ev_count=body.ev_count,
            transformer_kva=body.transformer_kva,
        )
    except Exception as exc:
        logger.error("grid_simulate_failed", error=str(exc))
        result = {
            "transformer_load_percent": 0.0,
            "after_peakbridge_percent": 0.0,
            "peak_reduction": 0.0,
            "status": "정상",
            "bus_voltages": [],
            "recommendation": "시뮬레이션 일시 불가",
            "engine": "error-fallback",
        }
    return success_response(result)


@router.get("/simulation/{building_id}")
async def get_grid_simulation(session: DbSession, building_id: str) -> dict:
    """
    GET /api/v1/grid/simulation/{building_id}

    DB 최신 센서값 기반 실시간 배전망 시뮬레이션.
    """
    grid_current = 0.0
    ess_soc = 0.0
    ess_available = False
    ev_count = 0

    try:
        sensor_repo = SensorRepository(session)
        device_repo = DeviceRepository(session)

        grid = await sensor_repo.get_latest_by_building(
            building_id, SensorType.GRID_CURRENT.value, DeviceType.GRID_METER.value
        )
        if grid:
            grid_current = grid.value

        ess = await sensor_repo.get_latest_by_building(
            building_id, SensorType.ESS_SOC.value, DeviceType.ESS.value
        )
        if ess:
            ess_soc = ess.value
            ess_available = True

        chargers = await device_repo.list_by_building(
            building_id, DeviceType.CHARGER.value
        )
        ev_count = len(chargers)
    except Exception as exc:
        logger.warning("grid_simulation_db_failed", building_id=building_id, error=str(exc))

    from app.core.config import settings

    ess_discharge_kw = 5.0 if (ess_available and ess_soc > settings.ESS_MIN_SOC) else 0.0

    try:
        result = grid_simulator.simulate(
            grid_current=grid_current,
            ess_discharge_kw=ess_discharge_kw,
            ev_count=ev_count,
        )
        model = grid_simulator.get_apartment_model(
            grid_current=grid_current, ev_count=ev_count
        )
    except Exception as exc:
        logger.error("grid_simulation_failed", building_id=building_id, error=str(exc))
        result, model = {}, {}

    return success_response(
        {
            "building_id": building_id,
            "inputs": {
                "grid_current": grid_current,
                "ess_soc": ess_soc,
                "ess_available": ess_available,
                "ev_count": ev_count,
                "ess_discharge_kw": ess_discharge_kw,
            },
            "simulation": result,
            "apartment_model": model,
        }
    )

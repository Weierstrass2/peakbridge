"""VPP(가상발전소) API — 포트폴리오·수요반응·차익거래 수익."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.constants import DeviceType, SensorType
from app.core.deps import DbSession
from app.ml.energy_optimizer import EnergyOptimizer
from app.ml.vpp_simulator import vpp_simulator
from app.repositories.device_repository import DeviceRepository
from app.repositories.sensor_repository import SensorRepository
from app.schemas.response import success_response
from app.services.kepco_service import KepcoService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/vpp", tags=["vpp"])

optimizer = EnergyOptimizer()

# 시연 포트폴리오: 실단지(building-A, DB 연동) + 확장 예시 단지
DEMO_BUILDINGS = [
    {"building_id": "building-B", "ess_capacity": 200.0, "current_soc": 65.0, "max_power_kw": 100.0},
    {"building_id": "building-C", "ess_capacity": 150.0, "current_soc": 80.0, "max_power_kw": 75.0},
]


async def _live_building(session) -> dict:
    """building-A 실측 SOC 기반 항목."""
    soc = 50.0
    try:
        sensor_repo = SensorRepository(session)
        reading = await sensor_repo.get_latest_by_building(
            "building-A", SensorType.ESS_SOC.value, DeviceType.ESS.value
        )
        if reading:
            soc = reading.value
    except Exception as exc:
        logger.warning("vpp_live_soc_failed", error=str(exc))
    return {
        "building_id": "building-A",
        "ess_capacity": 100.0,
        "current_soc": soc,
        "max_power_kw": 50.0,
        "live": True,
    }


async def _current_smp() -> float:
    try:
        return await KepcoService().get_current_smp()
    except Exception as exc:
        logger.warning("vpp_smp_failed_fallback", error=str(exc))
        return float(optimizer.get_current_rate()["rate"])


@router.get("/portfolio")
async def get_portfolio(session: DbSession) -> dict:
    """GET /api/v1/vpp/portfolio — 통합 포트폴리오 (building-A는 실측)."""
    buildings = [await _live_building(session), *DEMO_BUILDINGS]
    result = vpp_simulator.calculate_portfolio(buildings)
    result["note"] = "building-A 실측, B/C는 확장 예시"
    return success_response(result)


@router.get("/capacity")
async def get_capacity(session: DbSession) -> dict:
    """GET /api/v1/vpp/capacity — 가용 유연성 요약."""
    buildings = [await _live_building(session), *DEMO_BUILDINGS]
    p = vpp_simulator.calculate_portfolio(buildings)
    return success_response(
        {
            "total_capacity_kwh": p["total_capacity_kwh"],
            "available_flexibility_kw": p["available_flexibility_kw"],
            "building_count": p["building_count"],
        }
    )


@router.get("/revenue/dr")
async def get_dr_revenue(
    session: DbSession,
    reduction_kw: float = Query(default=None, ge=0, le=10000),
    duration_hours: float = Query(default=1.0, gt=0, le=24),
) -> dict:
    """GET /api/v1/vpp/revenue/dr — 수요반응 수익 (기본: 현재 가용 유연성 전량)."""
    smp = await _current_smp()
    if reduction_kw is None:
        buildings = [await _live_building(session), *DEMO_BUILDINGS]
        reduction_kw = vpp_simulator.calculate_portfolio(buildings)[
            "available_flexibility_kw"
        ]
    result = vpp_simulator.calculate_dr_revenue(reduction_kw, duration_hours, smp)
    return success_response(result)


@router.get("/revenue/arbitrage")
async def get_arbitrage_revenue(
    charged_kwh: float = Query(default=100.0, ge=0, le=100000),
    discharged_kwh: float = Query(default=90.0, ge=0, le=100000),
) -> dict:
    """GET /api/v1/vpp/revenue/arbitrage — 경부하 충전 → 최대부하 방전 차익."""
    try:
        season = optimizer._get_season(__import__("datetime").datetime.now())
        charge_price = optimizer.RATES[season]["경부하"]
        discharge_price = optimizer.RATES[season]["최대부하"]
    except Exception:
        charge_price, discharge_price = 42.5, 147.0
    result = vpp_simulator.calculate_arbitrage(
        charged_kwh, discharged_kwh, charge_price, discharge_price
    )
    result["charge_price"] = charge_price
    result["discharge_price"] = discharge_price
    return success_response(result)

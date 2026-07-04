"""
StateCollector — AI 의사결정용 15개 상태 변수 통합 수집.

DB 센서값 + 기상청 + SMP + 요금 + 배전망 시뮬레이터를 한 번에 모아
{grid_current, ess_soc, ..., rolling_mean_3h} 딕셔너리로 반환합니다.
모든 외부 소스는 개별 try/except — 일부 실패해도 나머지는 반환 (500 금지).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DeviceType, SensorType
from app.ml.energy_optimizer import EnergyOptimizer
from app.ml.grid_simulator import grid_simulator
from app.repositories.device_repository import DeviceRepository
from app.repositories.sensor_repository import SensorRepository
from app.services.kepco_service import KepcoService
from app.services.weather_service import WeatherService

logger = structlog.get_logger(__name__)

SEASON_CODE = {"여름철": 0, "봄가을철": 1, "겨울철": 2}
KST = timezone(timedelta(hours=9))


class StateCollector:
    """15개 변수 통합 수집기."""

    def __init__(self) -> None:
        self.optimizer = EnergyOptimizer()
        self.weather = WeatherService()
        self.kepco = KepcoService()

    async def collect(self, building_id: str, db: AsyncSession) -> dict:
        now_kst = datetime.now(KST)
        state: dict = {
            # 기본값 (수집 실패 시 유지)
            "grid_current": 0.0,
            "ess_soc": 0.0,
            "ess_available": 0,
            "current_temp": 20.0,
            "tomorrow_max_temp": 25.0,
            "smp_price": 42.5,
            "tariff_rate": 42.5,
            "hour": now_kst.hour,
            "weekday": now_kst.weekday(),
            "season": 1,
            "is_holiday": 0,
            "transformer_load": 0.0,
            "charger_count": 0,
            "lag_1h": 0.0,
            "rolling_mean_3h": 0.0,
        }

        sensor_repo = SensorRepository(db)
        device_repo = DeviceRepository(db)

        # ── DB: 그리드 전류 / ESS SOC / 충전기 수 ──────────
        grid_device_id: str | None = None
        try:
            grid = await sensor_repo.get_latest_by_building(
                building_id, SensorType.GRID_CURRENT.value, DeviceType.GRID_METER.value
            )
            if grid:
                state["grid_current"] = round(float(grid.value), 2)
                grid_device_id = grid.device_id
        except Exception as exc:
            logger.warning("state_grid_failed", error=str(exc))

        try:
            ess = await sensor_repo.get_latest_by_building(
                building_id, SensorType.ESS_SOC.value, DeviceType.ESS.value
            )
            if ess:
                state["ess_soc"] = round(float(ess.value), 1)
                state["ess_available"] = 1
        except Exception as exc:
            logger.warning("state_ess_failed", error=str(exc))

        try:
            chargers = await device_repo.list_by_building(
                building_id, DeviceType.CHARGER.value
            )
            state["charger_count"] = len(chargers)
        except Exception as exc:
            logger.warning("state_chargers_failed", error=str(exc))

        # ── 시계열 파생: lag_1h / rolling_mean_3h ─────────
        if grid_device_id:
            try:
                now_utc = datetime.now(timezone.utc)
                rows = await sensor_repo.get_aggregated_history(
                    grid_device_id, now_utc - timedelta(hours=3), now_utc, "1hour"
                )
                if rows:
                    values = [float(r["avg_value"]) for r in rows]
                    state["rolling_mean_3h"] = round(sum(values) / len(values), 2)
                    if len(rows) >= 2:
                        state["lag_1h"] = round(float(rows[-2]["avg_value"]), 2)
                    else:
                        state["lag_1h"] = round(values[-1], 2)
            except Exception as exc:
                logger.warning("state_timeseries_failed", error=str(exc))

        # ── 기상청 ────────────────────────────────────────
        try:
            state["current_temp"] = round(float(await self.weather.get_current_temperature()), 1)
        except Exception as exc:
            logger.warning("state_temp_failed", error=str(exc))
        try:
            state["tomorrow_max_temp"] = round(float(await self.weather.get_tomorrow_max_temp()), 1)
        except Exception as exc:
            logger.warning("state_tomorrow_failed", error=str(exc))

        # ── SMP / 요금 / 달력 ─────────────────────────────
        try:
            state["smp_price"] = round(float(await self.kepco.get_current_smp()), 1)
        except Exception as exc:
            logger.warning("state_smp_failed", error=str(exc))

        try:
            rate_info = self.optimizer.get_current_rate(now_kst.replace(tzinfo=None))
            state["tariff_rate"] = float(rate_info["rate"])
            state["season"] = SEASON_CODE.get(rate_info["season"], 1)
        except Exception as exc:
            logger.warning("state_tariff_failed", error=str(exc))

        try:
            state["is_holiday"] = int(
                self.optimizer._is_holiday(now_kst.replace(tzinfo=None))
            )
        except Exception:
            pass

        # ── 변압기 부하율 (배전망 시뮬레이터) ──────────────
        try:
            sim = grid_simulator.simulate(
                grid_current=state["grid_current"],
                ess_discharge_kw=0.0,
                ev_count=state["charger_count"],
            )
            state["transformer_load"] = sim["transformer_load_percent"]
        except Exception as exc:
            logger.warning("state_transformer_failed", error=str(exc))

        return state


state_collector = StateCollector()

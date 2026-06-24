"""
피크 감지 및 피크쉐이빙 자동 제어 서비스.

그리드 전류 임계치 초과 시 알림 생성, ESS 방전 명령, 절감량 계산.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.realtime import ws_manager
from app.core.config import settings
from app.core.constants import AlertSeverity, AlertType, ControlAction, TriggerSource
from app.models.alert import Alert
from app.models.control_log import ControlLog
from app.mqtt.publisher import MQTTPublisher
from app.repositories.alert_repository import AlertRepository
from app.repositories.control_log_repository import ControlLogRepository
from app.repositories.device_repository import DeviceRepository
from app.repositories.energy_repository import EnergyRepository

logger = structlog.get_logger(__name__)

# 건물별 피크 활성 상태 (in-memory)
_peak_state: dict[str, bool] = {}

# CO2 배출 계수 (kg/kWh)
CO2_FACTOR = 0.45


class PeakService:
    """피크 감지·쉐이빙·해제 비즈니스 로직."""

    def __init__(
        self,
        session: AsyncSession,
        mqtt: MQTTPublisher | None = None,
    ) -> None:
        self.session = session
        self.mqtt = mqtt
        self.alert_repo = AlertRepository(session)
        self.energy_repo = EnergyRepository(session)
        self.control_repo = ControlLogRepository(session)
        self.device_repo = DeviceRepository(session)

    @property
    def threshold(self) -> float:
        return settings.PEAK_THRESHOLD_A

    def is_peak(self, grid_current: float) -> bool:
        """전류가 임계치를 초과하는지 (경계값 포함: > threshold)."""
        return grid_current > self.threshold

    async def evaluate(
        self,
        building_id: str,
        grid_current: float,
        ess_soc: float,
    ) -> dict:
        """
        피크 상태 평가 및 자동 대응.

        Returns: {peak_triggered, peak_active, action_taken}
        """
        result = {
            "peak_triggered": False,
            "peak_active": _peak_state.get(building_id, False),
            "action_taken": None,
        }

        if self.is_peak(grid_current):
            if not _peak_state.get(building_id, False):
                await self._handle_peak_start(building_id, grid_current, ess_soc)
                result["peak_triggered"] = True
                result["peak_active"] = True

                action = await self._trigger_shaving(
                    building_id, grid_current, ess_soc
                )
                result["action_taken"] = action
            else:
                result["peak_active"] = True
        else:
            if _peak_state.get(building_id, False):
                await self._handle_peak_end(building_id, grid_current, ess_soc)
                result["peak_active"] = False

        return result

    async def _handle_peak_start(
        self, building_id: str, grid_current: float, ess_soc: float
    ) -> None:
        """피크 감지 알림 생성."""
        _peak_state[building_id] = True
        alert = Alert(
            id=uuid.uuid4(),
            building_id=building_id,
            alert_type=AlertType.PEAK_DETECTED.value,
            severity=AlertSeverity.WARNING.value
            if grid_current < self.threshold * 1.2
            else AlertSeverity.CRITICAL.value,
            grid_current=grid_current,
            ess_soc=ess_soc,
        )
        await self.alert_repo.create(alert)
        await ws_manager.send_peak_alert(building_id, grid_current, ess_soc)
        logger.info(
            "peak_detected",
            building_id=building_id,
            grid_current=grid_current,
            ess_soc=ess_soc,
        )

    async def _trigger_shaving(
        self, building_id: str, grid_current: float, ess_soc: float
    ) -> str | None:
        """ESS SOC > 20% 이면 discharge 명령."""
        if ess_soc <= settings.ESS_MIN_SOC:
            logger.warning(
                "peak_shaving_skipped_low_soc",
                building_id=building_id,
                ess_soc=ess_soc,
            )
            return None

        devices = await self.device_repo.list_by_building(building_id, "ess")
        device_id = devices[0].device_id if devices else f"{building_id}-ess"

        reduction = min(
            100.0,
            ((grid_current - self.threshold) / self.threshold) * 100,
        )

        alert = Alert(
            id=uuid.uuid4(),
            building_id=building_id,
            alert_type=AlertType.PEAK_SHAVING_ACTIVATED.value,
            severity=AlertSeverity.CRITICAL.value,
            grid_current=grid_current,
            ess_soc=ess_soc,
            reduction_percent=reduction,
        )
        await self.alert_repo.create(alert)

        if self.mqtt:
            await self.mqtt.publish_relay_control(
                building_id, ControlAction.DISCHARGE.value, TriggerSource.AI_AUTO.value
            )

        log = ControlLog(
            id=uuid.uuid4(),
            device_id=device_id,
            building_id=building_id,
            action=ControlAction.DISCHARGE.value,
            triggered_by=TriggerSource.AI_AUTO.value,
            ess_soc_before=ess_soc,
        )
        await self.control_repo.create(log)
        await ws_manager.send_control_executed(
            building_id, ControlAction.DISCHARGE.value, device_id
        )

        await self._record_savings(building_id, grid_current, reduction)
        return ControlAction.DISCHARGE.value

    async def _handle_peak_end(
        self, building_id: str, grid_current: float, ess_soc: float
    ) -> None:
        """피크 해제 처리."""
        _peak_state[building_id] = False
        alert = Alert(
            id=uuid.uuid4(),
            building_id=building_id,
            alert_type=AlertType.PEAK_RESOLVED.value,
            severity=AlertSeverity.WARNING.value,
            grid_current=grid_current,
            ess_soc=ess_soc,
        )
        await self.alert_repo.create(alert)
        await self.alert_repo.resolve_all_peak(building_id)
        await ws_manager.send_peak_resolved(building_id)
        logger.info("peak_resolved", building_id=building_id)

    async def _record_savings(
        self, building_id: str, grid_current: float, reduction_percent: float
    ) -> None:
        """피크쉐이빙 절감량 계산 및 저장."""
        excess_a = max(0.0, grid_current - self.threshold)
        # 5분 간격 기준 kWh 추정 (220V 3상 근사)
        saved_kwh = (excess_a * 220 * 3 / 1000) * (5 / 60) * (reduction_percent / 100)
        saved_won = saved_kwh * settings.PEAK_KWH_PRICE
        co2 = saved_kwh * CO2_FACTOR

        await self.energy_repo.increment_savings(
            building_id=building_id,
            saved_kwh=saved_kwh,
            saved_won=saved_won,
            co2_reduced_kg=co2,
            peak_inc=1,
        )

    def reset_state(self, building_id: str | None = None) -> None:
        """테스트용 피크 상태 초기화."""
        if building_id:
            _peak_state.pop(building_id, None)
        else:
            _peak_state.clear()

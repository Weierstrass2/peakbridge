"""시나리오 기반 자동 제어 서비스."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

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
from app.repositories.sensor_repository import SensorRepository
from app.services.kepco_service import KepcoService
from app.services.weather_service import WeatherService


def _now_kst():
    """KST 벽시계 (서버가 UTC여도 한국 시간 기준으로 판정)."""
    from datetime import datetime as _dt, timedelta as _td
    return _dt.utcnow() + _td(hours=9)


logger = structlog.get_logger(__name__)

# 건물별 자동 제어 모드 상태 (in-memory)
_auto_mode_state: dict[str, bool] = {}
# 건물별 임계치 상태 (in-memory)
_threshold_state: dict[str, float] = {}
# 시연용 가상 시각 오버라이드 (in-memory). 예측 파이프라인에만 영향 —
# 실제 피크 판정·제어는 항상 실제 시각을 쓴다(안전). None이면 실시간.
_demo_now_utc: datetime | None = None

# ESS 런타임(하드웨어 브리지가 올린 잔여 가동시간·SOC). in-memory, 신선도 체크용 시각 포함.
_ess_runtime_state: dict[str, dict] = {}

# ESS SOC 수동 리셋 요청 (in-memory). 대시보드 버튼 → 하드웨어 브리지가 폴링해
# MQTT command로 펌웨어 쿨롱 카운터를 리셋한다. 릴레이 직접 제어가 아니라
# SOC 기준값만 보정하는 경로 — 통신이 끊겨도 하드웨어 판단에는 영향 없다.
_soc_reset_state: dict[str, dict] = {}


def request_soc_reset(building_id: str, percent: float = 100.0) -> dict:
    """SOC 리셋 요청 등록. id(ms 타임스탬프)로 브리지가 신규 여부를 판별한다."""
    req = {
        "id": int(datetime.now(timezone.utc).timestamp() * 1000),
        "percent": percent,
    }
    _soc_reset_state[building_id] = req
    logger.info("soc_reset_requested", building_id=building_id, percent=percent)
    return req


def get_soc_reset(building_id: str, max_age_s: float = 120.0) -> dict | None:
    """대기 중인 SOC 리셋 요청 (기본 120초 이내만 유효 — 늦게 뜬 브리지가
    수 시간 전 요청을 뒤늦게 실행하는 것 방지)."""
    req = _soc_reset_state.get(building_id)
    if not req:
        return None
    if datetime.now(timezone.utc).timestamp() * 1000 - req["id"] > max_age_s * 1000:
        return None
    return req


# 강제 방전 모드 (in-memory 토글). 대시보드 버튼 → 브리지가 폴링해 MQTT command로
# 펌웨어에 전파. on이면 부하 무관 NO 유지, off면 자동 판단 복귀. id는 변경 시각(ms)으로,
# 브리지가 상태 변화를 감지하는 데 쓴다.
_force_discharge_state: dict[str, dict] = {}


def set_force_discharge(building_id: str, on: bool) -> dict:
    """강제 방전 모드 on/off 설정. id(ms)로 브리지가 변경 여부를 판별한다."""
    req = {
        "on": on,
        "id": int(datetime.now(timezone.utc).timestamp() * 1000),
    }
    _force_discharge_state[building_id] = req
    logger.info("force_discharge_set", building_id=building_id, on=on)
    return req


def get_force_discharge(building_id: str) -> dict | None:
    """현재 강제 방전 상태 (없으면 None). 토글 상태라 TTL 없이 마지막 값을 유지 —
    브리지가 재기동해도 현재 원하는 상태를 그대로 반영한다."""
    return _force_discharge_state.get(building_id)


def set_ess_runtime(
    building_id: str,
    remain_hours: float,
    soc: float | None,
    battery_temp_c: float | None = None,
    inverter_temp_c: float | None = None,
    thermal_lock: bool | None = None,
    relay_state: str | None = None,
    ina_current_ma: float | None = None,
    threshold_high_a: float | None = None,
    hold_remaining_s: float | None = None,
) -> None:
    """하드웨어 브리지가 올린 ESS 잔여 가동시간(h)·SOC(%) + 열 차단 + 실시간 릴레이/계측 상태 저장."""
    _ess_runtime_state[building_id] = {
        "remain_hours": remain_hours,
        "soc": soc,
        "battery_temp_c": battery_temp_c,
        "inverter_temp_c": inverter_temp_c,
        "thermal_lock": thermal_lock,
        "relay_state": relay_state,
        "ina_current_ma": ina_current_ma,
        "threshold_high_a": threshold_high_a,
        "hold_remaining_s": hold_remaining_s,
        "updated_at": datetime.now(timezone.utc).timestamp(),
    }


def get_ess_runtime(building_id: str, max_age_s: float = 30.0) -> dict | None:
    """신선한(기본 30초 이내) ESS 런타임만 반환. 오래됐거나 없으면 None."""
    rt = _ess_runtime_state.get(building_id)
    if not rt:
        return None
    if datetime.now(timezone.utc).timestamp() - rt["updated_at"] > max_age_s:
        return None
    return rt


def set_demo_time(dt_utc: datetime | None) -> None:
    """시연용 가상 시각 설정. None이면 실시간 복원."""
    global _demo_now_utc
    _demo_now_utc = dt_utc
    logger.info("demo_time_set", value=dt_utc.isoformat() if dt_utc else None)


def get_demo_time() -> datetime | None:
    """설정된 가상 시각 (없으면 None)."""
    return _demo_now_utc


def effective_now_utc() -> datetime:
    """예측용 유효 시각 — 데모 오버라이드가 있으면 그것, 없으면 실제 UTC now."""
    return _demo_now_utc or datetime.now(timezone.utc)


def get_auto_mode(building_id: str) -> bool:
    """건물별 자동 제어 모드 상태 조회."""
    return _auto_mode_state.get(building_id, True)


def set_auto_mode(building_id: str, enabled: bool) -> None:
    """건물별 자동 제어 모드 상태 설정."""
    _auto_mode_state[building_id] = enabled
    logger.info("auto_mode_changed", building_id=building_id, enabled=enabled)


def get_threshold(building_id: str) -> float:
    """건물별 임계치 조회."""
    return _threshold_state.get(building_id, settings.PEAK_THRESHOLD_A)


def set_threshold(building_id: str, value: float) -> None:
    """건물별 임계치 설정."""
    _threshold_state[building_id] = value
    logger.info("threshold_changed", building_id=building_id, value=value)


class ScenarioService:
    """시나리오 평가 및 자동 제어 서비스."""

    def __init__(
        self,
        session: AsyncSession,
        mqtt: MQTTPublisher | None = None,
    ):
        self.session = session
        self.mqtt = mqtt
        self.alert_repo = AlertRepository(session)
        self.control_repo = ControlLogRepository(session)
        self.device_repo = DeviceRepository(session)
        self.sensor_repo = SensorRepository(session)
        self.weather_service = WeatherService()
        self.kepco_service = KepcoService()

    async def evaluate_scenarios(self, building_id: str) -> list[dict]:
        """5가지 시나리오 평가."""
        scenarios = []

        # 1. peak_detect
        try:
            has_peak = await self.alert_repo.has_active_peak(building_id)
            scenarios.append({
                "id": "peak_detect",
                "name": "피크 감지",
                "active": has_peak,
                "value": 1.0 if has_peak else 0.0,
                "action_taken": False,
            })
        except Exception as exc:
            logger.error("scenario_peak_detect_failed", error=str(exc))
            scenarios.append({
                "id": "peak_detect",
                "name": "피크 감지",
                "active": False,
                "value": 0.0,
                "action_taken": False,
            })

        # 2. heatwave
        try:
            current_temp = await self.weather_service.get_current_temperature()
            is_heatwave = current_temp >= 33.0
            scenarios.append({
                "id": "heatwave",
                "name": "폭염 대응",
                "active": is_heatwave,
                "value": current_temp,
                "action_taken": False,
            })
        except Exception as exc:
            logger.error("scenario_heatwave_failed", error=str(exc))
            scenarios.append({
                "id": "heatwave",
                "name": "폭염 대응",
                "active": False,
                "value": 0.0,
                "action_taken": False,
            })

        # 3. night_charge
        now = _now_kst()
        hour = now.hour
        is_night = 23 <= hour or hour < 9
        scenarios.append({
            "id": "night_charge",
            "name": "심야 최적 충전",
            "active": is_night,
            "value": float(hour),
            "action_taken": False,
        })

        # 4. transformer_guard
        try:
            grid_reading = await self.sensor_repo.get_latest_by_building(
                building_id, "grid_current", "grid_meter"
            )
            grid_current = grid_reading.value if grid_reading else 0.0
            threshold = get_threshold(building_id)
            # 데이터 신선도 가드: 10분 넘은 측정값으로는 경보하지 않음
            fresh = False
            if grid_reading and grid_reading.recorded_at:
                from datetime import datetime, timezone

                age = (
                    datetime.now(timezone.utc)
                    - grid_reading.recorded_at.replace(tzinfo=timezone.utc)
                ).total_seconds()
                fresh = age <= 600
            is_guard = fresh and grid_current >= threshold * 0.9
            scenarios.append({
                "id": "transformer_guard",
                "name": "변압기 한계 감시",
                "active": is_guard,
                "value": grid_current,
                "action_taken": False,
            })
        except Exception as exc:
            logger.error("scenario_transformer_guard_failed", error=str(exc))
            scenarios.append({
                "id": "transformer_guard",
                "name": "변압기 한계 감시",
                "active": False,
                "value": 0.0,
                "action_taken": False,
            })

        # 5. vpp_dr
        try:
            smp = await self.kepco_service.get_current_smp()
            is_dr = smp >= settings.SMP_DR_THRESHOLD
            scenarios.append({
                "id": "vpp_dr",
                "name": "VPP 수요반응 대기",
                "active": is_dr,
                "value": smp,
                "action_taken": False,
            })
        except Exception as exc:
            logger.error("scenario_vpp_dr_failed", error=str(exc))
            scenarios.append({
                "id": "vpp_dr",
                "name": "VPP 수요반응 대기",
                "active": False,
                "value": 0.0,
                "action_taken": False,
            })

        return scenarios

    async def execute_auto_control(self, building_id: str) -> dict:
        """시나리오 기반 자동 제어 실행 (우선순위 적용)."""
        if not settings.SCENARIO_AUTO_CONTROL:
            return {"status": "skipped", "reason": "SCENARIO_AUTO_CONTROL is false"}

        if not get_auto_mode(building_id):
            return {"status": "skipped", "reason": "auto mode is disabled"}

        # 최근 30분 내 동일 액션 확인
        last_action = await self.control_repo.get_last_action(
            building_id, within_seconds=1800
        )

        scenarios = await self.evaluate_scenarios(building_id)
        scenario_map = {s["id"]: s for s in scenarios}

        # ESS SOC 조회
        ess_reading = await self.sensor_repo.get_latest_by_building(
            building_id, "ess_soc", "ess"
        )
        ess_soc = ess_reading.value if ess_reading else 50.0

        # 디바이스 조회
        devices = await self.device_repo.list_by_building(building_id, "ess")
        device_id = devices[0].device_id if devices else f"{building_id}-ess"

        # 우선순위: peak_detect → transformer_guard → vpp_dr → heatwave → night_charge
        action = None
        triggered_by = None
        reason = None

        # 1. peak_detect: PeakService가 처리하므로 skip
        if scenario_map["peak_detect"]["active"]:
            return {"status": "skipped", "reason": "peak_detect handled by PeakService"}

        # 2. transformer_guard
        if scenario_map["transformer_guard"]["active"]:
            if ess_soc > settings.ESS_MIN_SOC:
                if last_action and last_action.action == ControlAction.DISCHARGE.value:
                    return {"status": "skipped", "reason": "duplicate action within 30m"}
                action = ControlAction.DISCHARGE.value
                triggered_by = "scenario:transformer_guard"
                reason = "변압기 한계 감시 - 방전"

        # 3. vpp_dr
        if action is None and scenario_map["vpp_dr"]["active"]:
            if ess_soc > 40:
                if last_action and last_action.action == ControlAction.DISCHARGE.value:
                    return {"status": "skipped", "reason": "duplicate action within 30m"}
                action = ControlAction.DISCHARGE.value
                triggered_by = "scenario:vpp_dr"
                reason = "VPP 수요반응 - 방전"

        # 4. heatwave
        if action is None and scenario_map["heatwave"]["active"]:
            if ess_soc > 40:
                if last_action and last_action.action == ControlAction.DISCHARGE.value:
                    return {"status": "skipped", "reason": "duplicate action within 30m"}
                action = ControlAction.DISCHARGE.value
                triggered_by = "scenario:heatwave"
                reason = "폭염 대응 - 방전"

        # 5. night_charge
        if action is None and scenario_map["night_charge"]["active"]:
            if ess_soc < 85:
                if last_action and last_action.action == ControlAction.CHARGE.value:
                    return {"status": "skipped", "reason": "duplicate action within 30m"}
                action = ControlAction.CHARGE.value
                triggered_by = "scenario:night_charge"
                reason = "심야 최적 충전 - 충전"

        if action is None:
            return {"status": "no_action", "reason": "no scenario triggered"}

        # 액션 실행
        await self._execute_action(
            building_id=building_id,
            action=action,
            triggered_by=triggered_by,
            reason=reason,
            device_id=device_id,
            ess_soc=ess_soc,
        )

        return {
            "status": "executed",
            "action": action,
            "triggered_by": triggered_by,
            "reason": reason,
        }

    async def _execute_action(
        self,
        building_id: str,
        action: str,
        triggered_by: str,
        reason: str,
        device_id: str,
        ess_soc: float,
    ) -> None:
        """제어 액션 실행 (MQTT, 로그, 알림, WebSocket)."""
        # MQTT 발행
        if self.mqtt:
            await self.mqtt.publish_relay_control(
                building_id, action, triggered_by
            )

        # ControlLog 기록
        log = ControlLog(
            id=uuid.uuid4(),
            device_id=device_id,
            building_id=building_id,
            action=action,
            triggered_by=triggered_by,
            ess_soc_before=ess_soc,
        )
        await self.control_repo.create(log)

        # Alert 생성
        alert = Alert(
            id=uuid.uuid4(),
            building_id=building_id,
            alert_type=AlertType.PEAK_SHAVING_ACTIVATED.value,
            severity=AlertSeverity.WARNING.value,
            grid_current=0.0,
            ess_soc=ess_soc,
        )
        await self.alert_repo.create(alert)

        # WebSocket 브로드캐스트
        await ws_manager.send_control_executed(building_id, action, device_id)

        logger.info(
            "scenario_action_executed",
            building_id=building_id,
            action=action,
            triggered_by=triggered_by,
            reason=reason,
        )

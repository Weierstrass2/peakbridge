"""ESS 제어 API — 수동 릴레이 제어, 로그 조회, 임계치, 자동 모드, 충전기 제어."""

import uuid
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.v1.realtime import ws_manager
from app.core.constants import TriggerSource, AlertType, AlertSeverity
from app.core.deps import AdminOrManager, DbSession, get_mqtt_publisher
from app.core.exceptions import ConflictError, NotFoundError
from app.models.alert import Alert
from app.models.control_log import ControlLog
from app.repositories.alert_repository import AlertRepository
from app.repositories.control_log_repository import ControlLogRepository
from app.repositories.device_repository import DeviceRepository
from app.repositories.sensor_repository import SensorRepository
from app.schemas.api import RelayControlRequest
from app.schemas.response import success_response
from app.services.scenario_service import (
    get_auto_mode,
    set_auto_mode,
    get_threshold,
    set_threshold,
    set_demo_time,
    get_demo_time,
    set_ess_runtime,
    request_soc_reset,
    get_soc_reset,
)


class ThresholdRequest(BaseModel):
    # 실측 하드웨어 스케일(0.0x A)부터 대형 건물(수십 A)까지 수용
    value: float = Field(..., ge=0.01, le=100.0)


class AutoModeRequest(BaseModel):
    enabled: bool


class DemoTimeRequest(BaseModel):
    # 시연용 가상 시각(KST 0~23시). None이면 실시간 복원
    hour: Optional[int] = Field(None, ge=0, le=23)


class EssRuntimeRequest(BaseModel):
    # 하드웨어 브리지가 올리는 ESS 잔여 가동시간(h)·SOC(%)
    remain_hours: float = Field(..., ge=0.0)
    soc: Optional[float] = Field(None, ge=0.0, le=100.0)


class ChargerControlRequest(BaseModel):
    action: str  # "pause" or "resume"

router = APIRouter(prefix="/control", tags=["control"])


@router.post("/{building_id}/relay")
async def control_relay(
    session: DbSession,
    building_id: str,
    body: RelayControlRequest,
    user: AdminOrManager,
) -> dict:
    """
    POST /api/v1/control/{building_id}/relay

    JWT 인증 (admin|manager) + MQTT 발행 + ControlLog 기록.
    멱등성: 30초 내 동일 action 중복 방지.
    """
    control_repo = ControlLogRepository(session)
    device_repo = DeviceRepository(session)
    sensor_repo = SensorRepository(session)
    alert_repo_manual = AlertRepository(session)
    mqtt = get_mqtt_publisher()

    last = await control_repo.get_last_action(building_id, within_seconds=30)
    if last and last.action == body.action:
        raise ConflictError(
            f"Action '{body.action}' already executed within 30 seconds",
            code="DUPLICATE_ACTION",
        )

    devices = await device_repo.list_by_building(building_id, "ess")
    if not devices:
        raise NotFoundError("ESS device", building_id)
    device = devices[0]

    ess_reading = await sensor_repo.get_latest(device.device_id, "ess_soc")
    ess_soc = ess_reading.value if ess_reading else 0.0

    await mqtt.publish_relay_control(
        building_id, body.action, TriggerSource.MANUAL.value
    )

    log = ControlLog(
        id=uuid.uuid4(),
        device_id=device.device_id,
        building_id=building_id,
        action=body.action,
        triggered_by=TriggerSource.MANUAL.value,
        ess_soc_before=ess_soc,
    )
    await control_repo.create(log)

    # 수동 제어 알림 (Alerts 페이지 노출용)
    alert = Alert(
        id=uuid.uuid4(),
        building_id=building_id,
        alert_type=AlertType.MANUAL_CONTROL.value,
        severity=AlertSeverity.INFO.value,
        grid_current=0.0,
        ess_soc=ess_soc,
    )
    await alert_repo_manual.create(alert)
    await ws_manager.send_control_executed(building_id, body.action, device.device_id)

    return success_response(
        {
            "building_id": building_id,
            "action": body.action,
            "device_id": device.device_id,
            "triggered_by": user.email,
        }
    )


@router.get("/{building_id}/logs")
async def get_control_logs(
    session: DbSession,
    building_id: str,
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """제어 로그 조회 (최신순)."""
    control_repo = ControlLogRepository(session)
    logs = await control_repo.list_recent(building_id, limit)
    return success_response([
        {
            "id": str(log.id),
            "action": log.action,
            "triggered_by": log.triggered_by,
            "device_id": log.device_id,
            "ess_soc_before": log.ess_soc_before,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ])


@router.get("/{building_id}/settings")
async def get_settings(building_id: str) -> dict:
    """
    현장 기기(ESP32)·프론트 공용 설정 조회 — 현재 임계치와 자동 모드.

    무인증: 부팅 시 임계치 폴링용 (다른 조회성 엔드포인트와 동일 정책).
    """
    return success_response(
        {
            "building_id": building_id,
            "threshold": get_threshold(building_id),
            "auto_mode": get_auto_mode(building_id),
        }
    )


@router.put("/{building_id}/threshold")
async def update_threshold(
    building_id: str,
    request: ThresholdRequest,
    user: AdminOrManager,
) -> dict:
    """임계치 동적 변경 (0.1~100A) — MQTT config 토픽으로 현장 기기에도 전파."""
    set_threshold(building_id, request.value)
    mqtt = get_mqtt_publisher()
    mqtt_sent = await mqtt.publish_config(building_id, {"threshold": request.value})
    return success_response(
        {
            "building_id": building_id,
            "threshold": request.value,
            "mqtt_sent": mqtt_sent,
        }
    )


@router.post("/{building_id}/demo-time")
async def set_demo_time_endpoint(
    building_id: str,
    request: DemoTimeRequest,
    user: AdminOrManager,
) -> dict:
    """시연용 가상 시각 설정 (KST hour). hour=None이면 실시간 복원.

    예측 파이프라인에만 영향 — 피크 시간대(18~21시)로 옮기면 AI 예측선이
    상승해 '다음 피크 예상'이 뜬다. 실제 피크 판정·제어는 실제 시각 유지.
    """
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td

    if request.hour is None:
        set_demo_time(None)
        return success_response({"demo_time": None, "hour": None})

    # 오늘(KST) 그 시각을 UTC로 환산해 저장
    kst_now = _dt.utcnow() + _td(hours=9)
    kst_target = kst_now.replace(hour=request.hour, minute=0, second=0, microsecond=0)
    utc_target = (kst_target - _td(hours=9)).replace(tzinfo=_tz.utc)
    set_demo_time(utc_target)
    return success_response({"demo_time": utc_target.isoformat(), "hour": request.hour})


@router.post("/{building_id}/ess-runtime")
async def set_ess_runtime_endpoint(
    building_id: str,
    body: EssRuntimeRequest,
) -> dict:
    """하드웨어 브리지가 ESS 잔여 가동시간·SOC를 올리는 경로 (무인증 — 조회성 센서 업로드와 동일 정책).

    쿨롱 카운팅 SOC·방전율로 계산한 값. 대시보드가 30초 신선도로 표시한다.
    """
    set_ess_runtime(building_id, body.remain_hours, body.soc)
    return success_response({"building_id": building_id, "remain_hours": body.remain_hours})


@router.post("/{building_id}/ess-soc-reset")
async def reset_ess_soc(
    session: DbSession,
    building_id: str,
    user: AdminOrManager,
) -> dict:
    """ESS 잔량(SOC) 수동 100% 리셋 — 대시보드 버튼용.

    두 가지를 동시에 한다:
    1) 클라우드 DB에 ess_soc=100 측정값을 즉시 기록 → 대시보드가 다음 폴링(3초)에 반영.
       하드웨어 미연결 상태에서도 이것만으로 동작한다.
    2) in-memory 리셋 요청 등록 → 하드웨어 브리지가 GET /soc-reset 폴링으로 발견,
       MQTT command로 펌웨어 쿨롱 카운터를 100%로 보정 (안 하면 다음 텔레메트리가
       실측 SOC로 되덮는다). 릴레이 제어가 아니라 기준값 보정만 하는 안전한 경로.
    """
    from app.models.sensor_reading import SensorReading

    device_repo = DeviceRepository(session)
    sensor_repo = SensorRepository(session)

    # 기존 ESS 디바이스가 있으면 그것, 없으면 브리지 기본 ID로 생성
    ess_devices = await device_repo.list_by_building(building_id, "ess")
    if ess_devices:
        ess_device = ess_devices[0]
    else:
        ess_device = await device_repo.get_or_create(
            device_id="ESS-01", name="ESS-01", device_type="ess", building_id=building_id
        )

    await sensor_repo.create(
        SensorReading(
            device_id=ess_device.device_id,
            sensor_type="ess_soc",
            value=100.0,
            unit="%",
        )
    )
    req = request_soc_reset(building_id, 100.0)
    return success_response(
        {"building_id": building_id, "soc": 100.0, "request_id": req["id"]}
    )


@router.get("/{building_id}/soc-reset")
async def get_soc_reset_endpoint(building_id: str) -> dict:
    """하드웨어 브리지 폴링용 — 대기 중 SOC 리셋 요청 (무인증, 조회성 정책 동일).

    pending이 None이 아니면 브리지가 id 신규 여부를 보고 1회만 MQTT로 전파한다.
    """
    return success_response({"pending": get_soc_reset(building_id)})


@router.get("/{building_id}/auto-mode")
async def get_auto_mode_endpoint(
    building_id: str,
) -> dict:
    """자동 제어 모드 상태 조회."""
    enabled = get_auto_mode(building_id)
    return success_response({"enabled": enabled})


@router.post("/{building_id}/auto-mode")
async def set_auto_mode_endpoint(
    building_id: str,
    request: AutoModeRequest,
    user: AdminOrManager,
) -> dict:
    """자동 제어 모드 설정."""
    set_auto_mode(building_id, request.enabled)
    return success_response({"enabled": request.enabled})


@router.post("/{building_id}/charger/{device_id}")
async def control_charger(
    session: DbSession,
    building_id: str,
    device_id: str,
    request: ChargerControlRequest,
    user: AdminOrManager,
) -> dict:
    """충전기 개별 제어 (pause/resume)."""
    if request.action not in ["pause", "resume"]:
        raise ValueError("Action must be 'pause' or 'resume'")
    
    control_repo = ControlLogRepository(session)
    alert_repo = AlertRepository(session)
    sensor_repo = SensorRepository(session)
    mqtt = get_mqtt_publisher()

    # MQTT 발행
    await mqtt.publish_charger_control(building_id, device_id, request.action)

    # ControlLog 기록
    ess_reading = await sensor_repo.get_latest_by_building(
        building_id, "ess_soc", "ess"
    )
    ess_soc = ess_reading.value if ess_reading else 0.0

    log = ControlLog(
        id=uuid.uuid4(),
        device_id=device_id,
        building_id=building_id,
        action=request.action,
        triggered_by=TriggerSource.MANUAL.value,
        ess_soc_before=ess_soc,
    )
    await control_repo.create(log)

    # Alert 생성
    alert = Alert(
        id=uuid.uuid4(),
        building_id=building_id,
        alert_type=AlertType.CHARGER_CONTROL.value,
        severity=AlertSeverity.INFO.value,
        grid_current=0.0,
        ess_soc=ess_soc,
    )
    await alert_repo.create(alert)

    # WebSocket 브로드캐스트
    await ws_manager.send_control_executed(building_id, request.action, device_id)

    return success_response({
        "building_id": building_id,
        "device_id": device_id,
        "action": request.action,
    })

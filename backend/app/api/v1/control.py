"""ESS 제어 API — 수동 릴레이 제어, 로그 조회, 임계치, 자동 모드, 충전기 제어."""

import uuid
from typing import Optional

from fastapi import APIRouter, Query

from app.api.v1.realtime import ws_manager
from app.core.constants import TriggerSource
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
)

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


@router.put("/{building_id}/threshold")
async def update_threshold(
    building_id: str,
    value: float,
    user: AdminOrManager,
) -> dict:
    """임계치 동적 변경 (0.1~100A)."""
    if not (0.1 <= value <= 100.0):
        raise ValueError("Threshold must be between 0.1 and 100.0")
    set_threshold(building_id, value)
    return success_response({"building_id": building_id, "threshold": value})


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
    enabled: bool,
    user: AdminOrManager,
) -> dict:
    """자동 제어 모드 설정."""
    set_auto_mode(building_id, enabled)
    return success_response({"enabled": enabled})


@router.post("/{building_id}/charger/{device_id}")
async def control_charger(
    session: DbSession,
    building_id: str,
    device_id: str,
    action: str,
    user: AdminOrManager,
) -> dict:
    """충전기 개별 제어 (pause/resume)."""
    if action not in ["pause", "resume"]:
        raise ValueError("Action must be 'pause' or 'resume'")
    
    control_repo = ControlLogRepository(session)
    alert_repo = AlertRepository(session)
    sensor_repo = SensorRepository(session)
    mqtt = get_mqtt_publisher()

    # MQTT 발행
    await mqtt.publish_charger_control(building_id, device_id, action)

    # ControlLog 기록
    ess_reading = await sensor_repo.get_latest_by_building(
        building_id, "ess_soc", "ess"
    )
    ess_soc = ess_reading.value if ess_reading else 0.0

    log = ControlLog(
        id=uuid.uuid4(),
        device_id=device_id,
        building_id=building_id,
        action=action,
        triggered_by=TriggerSource.MANUAL.value,
        ess_soc_before=ess_soc,
    )
    await control_repo.create(log)

    # Alert 생성
    alert = Alert(
        id=uuid.uuid4(),
        building_id=building_id,
        alert_type="charger_control",
        severity="info",
        grid_current=0.0,
        ess_soc=ess_soc,
    )
    await alert_repo.create(alert)

    # WebSocket 브로드캐스트
    await ws_manager.send_control_executed(building_id, action, device_id)

    return success_response({
        "building_id": building_id,
        "device_id": device_id,
        "action": action,
    })

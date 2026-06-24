"""ESS 제어 API — 수동 릴레이 제어."""

import uuid

from fastapi import APIRouter

from app.api.v1.realtime import ws_manager
from app.core.constants import TriggerSource
from app.core.deps import AdminOrManager, DbSession, get_mqtt_publisher
from app.core.exceptions import ConflictError, NotFoundError
from app.models.control_log import ControlLog
from app.repositories.control_log_repository import ControlLogRepository
from app.repositories.device_repository import DeviceRepository
from app.repositories.sensor_repository import SensorRepository
from app.schemas.api import RelayControlRequest
from app.schemas.response import success_response

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

"""센서 API — 측정값 수집 및 이력 조회."""

from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app.core.deps import DbSession, get_mqtt_publisher
from app.core.exceptions import ValidationAppError
from app.schemas.api import SensorReadingBatchCreate, SensorReadingCreate
from app.schemas.response import success_response
from app.services.sensor_service import SensorService

router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.post("/readings")
async def create_readings(
    session: DbSession,
    body: SensorReadingBatchCreate,
) -> dict:
    """
    POST /api/v1/sensors/readings

    단일 또는 배치 센서 측정값 기록.
    """
    mqtt = get_mqtt_publisher()
    service = SensorService(session, mqtt)

    if body.readings:
        result = await service.record_batch(
            [r.model_dump() for r in body.readings]
        )
    elif body.device_id and body.sensor_type and body.value is not None:
        reading = SensorReadingCreate(
            device_id=body.device_id,
            sensor_type=body.sensor_type,
            value=body.value,
            unit=body.unit,
            building_id=body.building_id,
        )
        result = await service.record_reading(**reading.model_dump())
    else:
        raise ValidationAppError(
            "Provide either 'readings' array or device_id/sensor_type/value"
        )

    return success_response(
        {
            "status": result.get("status", "recorded"),
            "peak_triggered": result.get("peak_triggered", False),
            "forecast_next_hour": result.get("forecast_next_hour", []),
        }
    )


@router.get("/{device_id}/history")
async def get_sensor_history(
    session: DbSession,
    device_id: str,
    from_time: datetime = Query(default=None),
    to_time: datetime = Query(default=None),
    interval: str = Query(default="5min", pattern="^(1min|5min|1hour)$"),
) -> dict:
    """
    GET /api/v1/sensors/{device_id}/history

    시간대별 평균값 집계 이력.
    """
    now = datetime.now(timezone.utc)
    if from_time is None:
        from_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if to_time is None:
        to_time = now

    service = SensorService(session)
    history = await service.get_history(
        device_id=device_id,
        from_time=from_time,
        to_time=to_time,
        interval=interval,
    )
    return success_response({"device_id": device_id, "interval": interval, "history": history})

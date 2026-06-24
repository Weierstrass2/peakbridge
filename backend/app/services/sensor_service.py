"""
센서 데이터 수집 및 실시간 처리 서비스.

측정값 저장 → 피크 평가 → WebSocket 브로드캐스트.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.realtime import ws_manager
from app.core.constants import DeviceType, SensorType
from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.sensor_reading import SensorReading
from app.mqtt.publisher import MQTTPublisher
from app.repositories.device_repository import DeviceRepository
from app.repositories.sensor_repository import SensorRepository
from app.services.forecast_service import ForecastService
from app.services.peak_service import PeakService

logger = structlog.get_logger(__name__)

SENSOR_DEVICE_MAP = {
    SensorType.GRID_CURRENT.value: DeviceType.GRID_METER.value,
    SensorType.ESS_SOC.value: DeviceType.ESS.value,
    SensorType.CHARGER_CURRENT.value: DeviceType.CHARGER.value,
}


class SensorService:
    """센서 측정값 기록 및 연쇄 처리."""

    def __init__(
        self,
        session: AsyncSession,
        mqtt: MQTTPublisher | None = None,
    ) -> None:
        self.session = session
        self.mqtt = mqtt
        self.sensor_repo = SensorRepository(session)
        self.device_repo = DeviceRepository(session)
        self.peak_service = PeakService(session, mqtt)
        self.forecast_service = ForecastService(session)

    async def record_reading(
        self,
        device_id: str,
        sensor_type: str,
        value: float,
        unit: str,
        building_id: str | None = None,
    ) -> dict:
        """
        센서 측정값 기록 및 후속 처리.

        grid_current → peak_service.evaluate() 호출
        device last_seen_at 갱신
        WebSocket 실시간 브로드캐스트
        """
        device = await self.device_repo.get_by_device_id(device_id)
        if not device:
            if not building_id:
                raise NotFoundError("Device", device_id)
            device_type = SENSOR_DEVICE_MAP.get(sensor_type, DeviceType.GRID_METER.value)
            device = await self.device_repo.get_or_create(
                device_id=device_id,
                name=device_id,
                device_type=device_type,
                building_id=building_id,
            )

        bid = building_id or device.building_id

        reading = SensorReading(
            id=uuid.uuid4(),
            device_id=device_id,
            sensor_type=sensor_type,
            value=value,
            unit=unit,
        )
        await self.sensor_repo.create(reading)
        await self.device_repo.update_last_seen(device_id)

        await ws_manager.send_sensor_update(
            bid, device_id, sensor_type, value, unit
        )

        peak_result = {"peak_triggered": False, "peak_active": False}
        if sensor_type == SensorType.GRID_CURRENT.value:
            ess_reading = await self.sensor_repo.get_latest_by_building(
                bid, SensorType.ESS_SOC.value, DeviceType.ESS.value
            )
            ess_soc = ess_reading.value if ess_reading else 50.0
            peak_result = await self.peak_service.evaluate(bid, value, ess_soc)
        elif sensor_type == SensorType.ESS_SOC.value and peak_result.get("peak_active"):
            pass

        forecast = await self.forecast_service.get_next_hour_summary(bid)

        logger.info(
            "sensor_reading_recorded",
            device_id=device_id,
            sensor_type=sensor_type,
            value=value,
            building_id=bid,
        )

        return {
            "status": "recorded",
            "device_id": device_id,
            "building_id": bid,
            "peak_triggered": peak_result.get("peak_triggered", False),
            "peak_active": peak_result.get("peak_active", False),
            "forecast_next_hour": forecast,
        }

    async def record_batch(self, readings: list[dict]) -> dict:
        """배치 측정값 기록."""
        results = []
        last_peak = False
        last_forecast: list = []

        for item in readings:
            result = await self.record_reading(
                device_id=item["device_id"],
                sensor_type=item["sensor_type"],
                value=item["value"],
                unit=item.get("unit", "A"),
                building_id=item.get("building_id"),
            )
            results.append(result)
            last_peak = result.get("peak_triggered", False)
            last_forecast = result.get("forecast_next_hour", [])

        return {
            "status": "recorded",
            "count": len(results),
            "peak_triggered": last_peak,
            "forecast_next_hour": last_forecast,
            "results": results,
        }

    async def get_history(
        self,
        device_id: str,
        from_time: datetime,
        to_time: datetime,
        interval: str | None = None,
        sensor_type: str | None = None,
    ) -> list[dict]:
        """기간별 센서 이력 (집계 또는 원본)."""
        if interval:
            return await self.sensor_repo.get_aggregated_history(
                device_id, from_time, to_time, interval, sensor_type
            )
        readings = await self.sensor_repo.get_history(
            device_id, from_time, to_time, sensor_type
        )
        return [
            {
                "time": r.recorded_at,
                "value": r.value,
                "unit": r.unit,
                "sensor_type": r.sensor_type,
            }
            for r in readings
        ]

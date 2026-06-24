"""
MQTT 구독자 — 센서 데이터 수신 및 sensor_service 연동.

지수 백오프 재연결, QoS 1 보장.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from app.core.config import settings
from app.db.base import async_session_factory
from app.ml.anomaly import AnomalyDetector
from app.mqtt.publisher import mqtt_publisher

logger = structlog.get_logger(__name__)


class MQTTSubscriber:
    """aiomqtt 기반 비동기 MQTT 구독."""

    SUBSCRIBE_PATTERNS = [
        f"{settings.MQTT_TOPIC_PREFIX}/+/grid/current",
        f"{settings.MQTT_TOPIC_PREFIX}/+/ess/soc",
        f"{settings.MQTT_TOPIC_PREFIX}/+/charger/+/current",
    ]

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None
        self._detectors: dict[str, AnomalyDetector] = {}

    def _get_detector(self, sensor_type: str) -> AnomalyDetector:
        if sensor_type not in self._detectors:
            self._detectors[sensor_type] = AnomalyDetector(sensor_type)
        return self._detectors[sensor_type]

    async def start(self) -> None:
        """백그라운드 구독 태스크 시작."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("mqtt_subscriber_started")

    async def stop(self) -> None:
        """구독 중지."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("mqtt_subscriber_stopped")

    async def _run_loop(self) -> None:
        """지수 백오프 재연결 루프."""
        retry_delay = 1
        max_delay = 60

        while self._running:
            try:
                await self._subscribe()
                retry_delay = 1
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    "mqtt_subscriber_error",
                    error=str(exc),
                    retry_in=retry_delay,
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_delay)

    async def _subscribe(self) -> None:
        """토픽 구독 및 메시지 처리."""
        import aiomqtt

        kwargs: dict[str, Any] = {
            "hostname": settings.MQTT_HOST,
            "port": settings.MQTT_PORT,
        }
        if settings.MQTT_USERNAME:
            kwargs["username"] = settings.MQTT_USERNAME
            kwargs["password"] = settings.MQTT_PASSWORD

        async with aiomqtt.Client(**kwargs) as client:
            for pattern in self.SUBSCRIBE_PATTERNS:
                await client.subscribe(pattern, qos=aiomqtt.QoS(1))
            logger.info("mqtt_subscribed", patterns=self.SUBSCRIBE_PATTERNS)

            async for message in client.messages:
                if not self._running:
                    break
                await self._handle_message(message)

    async def _handle_message(self, message: Any) -> None:
        """수신 메시지 파싱 → 이상치 필터 → sensor_service 호출."""
        try:
            topic = str(message.topic)
            payload = json.loads(message.payload.decode())
            parsed = self._parse_topic(topic, payload)
            if not parsed:
                return

            device_id, sensor_type, value, unit, building_id = parsed
            detector = self._get_detector(sensor_type)

            if detector.is_sensor_error(value) or detector.detect(value):
                logger.warning(
                    "mqtt_anomaly_filtered",
                    device_id=device_id,
                    value=value,
                    sensor_type=sensor_type,
                )
                return

            from app.services.sensor_service import SensorService

            async with async_session_factory() as session:
                service = SensorService(session, mqtt_publisher)
                await service.record_reading(
                    device_id=device_id,
                    sensor_type=sensor_type,
                    value=value,
                    unit=unit,
                    building_id=building_id,
                )
                await session.commit()
        except Exception as exc:
            logger.error("mqtt_message_handle_failed", error=str(exc))

    def _parse_topic(
        self, topic: str, payload: dict
    ) -> tuple[str, str, float, str, str] | None:
        """
        MQTT 토픽 파싱.

        peakbridge/{building_id}/grid/current
        peakbridge/{building_id}/ess/soc
        peakbridge/{building_id}/charger/{device_id}/current
        """
        parts = topic.split("/")
        if len(parts) < 4:
            return None

        prefix = parts[0]
        if prefix != settings.MQTT_TOPIC_PREFIX:
            return None

        building_id = parts[1]
        value = float(payload.get("value", 0))
        unit = payload.get("unit", "A")

        if "grid" in topic and "current" in topic:
            device_id = payload.get("device_id", f"{building_id}-grid-meter")
            return device_id, "grid_current", value, unit, building_id
        if "ess" in topic and "soc" in topic:
            device_id = payload.get("device_id", f"{building_id}-ess")
            return device_id, "ess_soc", value, "%", building_id
        if "charger" in topic:
            device_id = parts[3] if len(parts) > 4 else payload.get("device_id", "")
            return device_id, "charger_current", value, unit, building_id

        return None


mqtt_subscriber = MQTTSubscriber()

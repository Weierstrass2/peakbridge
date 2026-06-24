"""MQTT 제어 명령 발행."""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


class MQTTPublisher:
    """aiomqtt 기반 비동기 MQTT 발행 클라이언트."""

    def __init__(self) -> None:
        self._client: Any = None

    async def connect(self) -> None:
        """MQTT 브로커 연결."""
        try:
            import aiomqtt

            kwargs: dict[str, Any] = {
                "hostname": settings.MQTT_HOST,
                "port": settings.MQTT_PORT,
            }
            if settings.MQTT_USERNAME:
                kwargs["username"] = settings.MQTT_USERNAME
                kwargs["password"] = settings.MQTT_PASSWORD

            self._client = aiomqtt.Client(**kwargs)
            await self._client.__aenter__()
            logger.info("mqtt_publisher_connected", host=settings.MQTT_HOST)
        except Exception as exc:
            logger.warning("mqtt_publisher_connect_failed", error=str(exc))
            self._client = None

    async def disconnect(self) -> None:
        """연결 종료."""
        if self._client:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                pass
            self._client = None

    async def publish(
        self, topic: str, payload: dict[str, Any], qos: int = 1
    ) -> bool:
        """토픽에 JSON payload 발행 (QoS 1)."""
        if not self._client:
            logger.warning("mqtt_publish_skipped_no_client", topic=topic)
            return False
        try:
            import aiomqtt

            await self._client.publish(
                topic,
                payload=json.dumps(payload),
                qos=aiomqtt.QoS(qos),
            )
            logger.info("mqtt_published", topic=topic, payload=payload)
            return True
        except Exception as exc:
            logger.error("mqtt_publish_failed", topic=topic, error=str(exc))
            return False

    async def publish_relay_control(
        self, building_id: str, action: str, triggered_by: str = "ai_auto"
    ) -> bool:
        """peakbridge/control/relay 토픽으로 ESS 제어 명령 발행."""
        topic = f"{settings.MQTT_TOPIC_PREFIX}/control/relay"
        payload = {
            "building_id": building_id,
            "action": action,
            "triggered_by": triggered_by,
        }
        return await self.publish(topic, payload, qos=1)


mqtt_publisher = MQTTPublisher()

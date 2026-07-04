"""
OpenADR 2.0b 호환 수요반응(DR) 서비스 — VTN/VEN 통합 시뮬레이션.

VTN(가상 전력거래소)이 이벤트를 발령하면 VEN(건물 클라이언트)이
신호를 해석해 ESS를 자동 제어합니다. openleadr 프로토콜 시맨틱
(SIMPLE 0~3, PRICE 신호)을 따르되, 시연 환경에서는 인프로세스로 동작합니다.
"""

from __future__ import annotations

import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

import structlog

from app.core.config import settings
from app.mqtt.publisher import mqtt_publisher

logger = structlog.get_logger(__name__)

# SIMPLE 신호 레벨 → ESS 대응 (OpenADR SIMPLE signal 표준 레벨)
SIMPLE_LEVELS: dict[int, dict[str, Any]] = {
    0: {"action": "standby", "discharge_percent": 0, "label": "정상 (대기)"},
    1: {"action": "discharge", "discharge_percent": 30, "label": "주의 — ESS 30% 방전"},
    2: {"action": "discharge", "discharge_percent": 70, "label": "경계 — ESS 70% 방전"},
    3: {"action": "discharge", "discharge_percent": 100, "label": "긴급 — ESS 100% 방전"},
}

PRICE_DISCHARGE_THRESHOLD = 200.0  # 원/kWh 이상 → 방전
PRICE_CHARGE_THRESHOLD = 80.0      # 원/kWh 이하 → 충전


class OpenADRService:
    """VTN(발령) + VEN(수신·대응) 통합 서비스."""

    def __init__(self) -> None:
        self._history: deque[dict] = deque(maxlen=100)
        self._active_event: dict | None = None
        self._ven_state: str = "idle"  # idle | responding

    # ── VEN: 신호 해석 ────────────────────────────────
    @staticmethod
    def _interpret(signal_type: str, value: float) -> dict[str, Any]:
        st = (signal_type or "").upper()
        if st == "SIMPLE":
            level = int(max(0, min(3, int(value))))
            plan = dict(SIMPLE_LEVELS[level])
            plan["level"] = level
            return plan
        if st == "PRICE":
            if value >= PRICE_DISCHARGE_THRESHOLD:
                return {
                    "action": "discharge", "discharge_percent": 100,
                    "label": f"고가격 {value:.0f}원 — 방전 시작", "level": None,
                }
            if value <= PRICE_CHARGE_THRESHOLD:
                return {
                    "action": "charge", "discharge_percent": 0,
                    "label": f"저가격 {value:.0f}원 — 충전 시작", "level": None,
                }
            return {
                "action": "standby", "discharge_percent": 0,
                "label": f"가격 {value:.0f}원 — 대기", "level": None,
            }
        return {"action": "standby", "discharge_percent": 0, "label": "알 수 없는 신호 — 대기", "level": None}

    # ── VTN: 이벤트 발령 → VEN 대응 ───────────────────
    async def handle_event(
        self,
        signal_type: str,
        value: float,
        building_id: str = "building-A",
        duration_minutes: int = 60,
    ) -> dict:
        """DR 이벤트 발령 및 자동 ESS 제어."""
        plan = self._interpret(signal_type, value)
        event = {
            "event_id": str(uuid.uuid4())[:8],
            "signal_type": (signal_type or "").upper(),
            "value": value,
            "building_id": building_id,
            "action": plan["action"],
            "discharge_percent": plan["discharge_percent"],
            "label": plan["label"],
            "duration_minutes": duration_minutes,
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "mqtt_sent": False,
        }

        # VEN 대응: MQTT로 ESS 제어 발행 (브로커 미연결 시에도 이벤트는 기록)
        try:
            sent = await mqtt_publisher.publish_relay_control(
                building_id, plan["action"], "openadr"
            )
            await mqtt_publisher.publish(
                f"{settings.MQTT_TOPIC_PREFIX}/{building_id}/ess/dr",
                {
                    "action": plan["action"],
                    "discharge_percent": plan["discharge_percent"],
                    "event_id": event["event_id"],
                    "triggered_by": "openadr",
                },
            )
            event["mqtt_sent"] = bool(sent)
        except Exception as exc:
            logger.warning("openadr_mqtt_failed", error=str(exc))

        self._active_event = event if plan["action"] != "standby" else None
        self._ven_state = "responding" if plan["action"] != "standby" else "idle"
        self._history.appendleft(event)

        logger.info(
            "openadr_event_handled",
            event_id=event["event_id"],
            signal=event["signal_type"],
            value=value,
            action=plan["action"],
        )
        return event

    # ── 조회 ─────────────────────────────────────────
    def get_status(self) -> dict:
        return {
            "vtn": {"role": "가상 전력거래소 (시뮬레이션)", "online": True},
            "ven": {
                "role": "건물 클라이언트",
                "state": self._ven_state,
                "registered": True,
            },
            "active_event": self._active_event,
            "signal_map": {
                "SIMPLE": {str(k): v["label"] for k, v in SIMPLE_LEVELS.items()},
                "PRICE": {
                    f">={PRICE_DISCHARGE_THRESHOLD:.0f}원": "방전 시작",
                    f"<={PRICE_CHARGE_THRESHOLD:.0f}원": "충전 시작",
                },
            },
        }

    def get_history(self, limit: int = 20) -> list[dict]:
        return list(self._history)[: max(1, min(100, limit))]


openadr_service = OpenADRService()

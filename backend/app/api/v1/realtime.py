"""WebSocket 실시간 이벤트 브로드캐스트."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import WebSocket

logger = structlog.get_logger(__name__)


class ConnectionManager:
    """
    건물별 WebSocket 연결 관리.

    메시지 타입: sensor_update, peak_alert, peak_resolved, control_executed
    """

    def __init__(self) -> None:
        # building_id → set of WebSocket connections
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, building_id: str, websocket: WebSocket) -> None:
        """연결 수락 및 등록."""
        await websocket.accept()
        async with self._lock:
            if building_id not in self._connections:
                self._connections[building_id] = set()
            self._connections[building_id].add(websocket)
        logger.info("ws_connected", building_id=building_id)

    async def disconnect(self, building_id: str, websocket: WebSocket) -> None:
        """연결 해제 및 정리."""
        async with self._lock:
            conns = self._connections.get(building_id, set())
            conns.discard(websocket)
            if not conns and building_id in self._connections:
                del self._connections[building_id]
        logger.info("ws_disconnected", building_id=building_id)

    async def broadcast(
        self, building_id: str, message_type: str, payload: dict[str, Any]
    ) -> None:
        """건물 내 모든 클라이언트에 메시지 브로드캐스트."""
        message = {
            "type": message_type,
            "data": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        async with self._lock:
            connections = list(self._connections.get(building_id, set()))

        dead: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            await self.disconnect(building_id, ws)

    async def send_sensor_update(
        self, building_id: str, device_id: str, sensor_type: str, value: float, unit: str
    ) -> None:
        """센서값 실시간 업데이트."""
        await self.broadcast(
            building_id,
            "sensor_update",
            {
                "device_id": device_id,
                "sensor_type": sensor_type,
                "value": value,
                "unit": unit,
            },
        )

    async def send_peak_alert(
        self, building_id: str, grid_current: float, ess_soc: float
    ) -> None:
        """피크 감지 이벤트."""
        await self.broadcast(
            building_id,
            "peak_alert",
            {"grid_current": grid_current, "ess_soc": ess_soc},
        )

    async def send_peak_resolved(self, building_id: str) -> None:
        """피크 해제 이벤트."""
        await self.broadcast(building_id, "peak_resolved", {})

    async def send_control_executed(
        self, building_id: str, action: str, device_id: str
    ) -> None:
        """제어 명령 실행 알림."""
        await self.broadcast(
            building_id,
            "control_executed",
            {"action": action, "device_id": device_id},
        )


# 애플리케이션 전역 싱글톤
ws_manager = ConnectionManager()

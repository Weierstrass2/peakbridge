"""WebSocket 실시간 API."""

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.v1.realtime import ws_manager
from app.core.security import decode_access_token

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/{building_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    building_id: str,
    token: str = Query(default=""),
) -> None:
    """
    WS /api/v1/ws/{building_id}

    JWT 토큰(쿼리 파라미터)으로 인증.
    """
    if not token or not decode_access_token(token):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await ws_manager.connect(building_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(building_id, websocket)

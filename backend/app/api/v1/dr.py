"""수요반응(DR) API — OpenADR VTN/VEN 이벤트 발령·조회."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.schemas.response import success_response
from app.services.openadr_service import openadr_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/dr", tags=["dr"])


class DREventRequest(BaseModel):
    """DR 이벤트 발령 요청."""

    signal_type: str = Field(default="SIMPLE", pattern="^(?i)(SIMPLE|PRICE)$")
    value: float = Field(ge=0, le=10000, description="SIMPLE: 0~3 레벨 / PRICE: 원/kWh")
    building_id: str = Field(default="building-A")
    duration_minutes: int = Field(default=60, ge=1, le=1440)


@router.post("/event")
async def issue_dr_event(body: DREventRequest) -> dict:
    """POST /api/v1/dr/event — VTN 이벤트 발령 → VEN 자동 대응."""
    try:
        event = await openadr_service.handle_event(
            signal_type=body.signal_type,
            value=body.value,
            building_id=body.building_id,
            duration_minutes=body.duration_minutes,
        )
    except Exception as exc:
        logger.error("dr_event_failed", error=str(exc))
        event = {"error": "이벤트 처리 일시 불가", "detail": str(exc)}
    return success_response(event)


@router.get("/status")
async def get_dr_status() -> dict:
    """GET /api/v1/dr/status — VTN/VEN 상태 및 활성 이벤트."""
    try:
        status = openadr_service.get_status()
    except Exception as exc:
        logger.error("dr_status_failed", error=str(exc))
        status = {"vtn": {"online": False}, "ven": {"state": "unknown"}}
    return success_response(status)


@router.get("/history")
async def get_dr_history(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    """GET /api/v1/dr/history — DR 이벤트 이력."""
    try:
        history = openadr_service.get_history(limit)
    except Exception as exc:
        logger.error("dr_history_failed", error=str(exc))
        history = []
    return success_response({"events": history, "count": len(history)})

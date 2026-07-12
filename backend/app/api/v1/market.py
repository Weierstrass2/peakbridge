"""전력시장(DAM) 입찰 API — 입찰서 작성·제출·개찰."""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.schemas.response import success_response
from app.services.market_service import market_service
from app.services.bid_ai import ai_bids

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/market", tags=["market"])


class BidItem(BaseModel):
    hour: int = Field(ge=0, le=23)
    qty_kw: float = Field(ge=0, le=500)
    price: float = Field(ge=0, le=500)


class BidSheet(BaseModel):
    bids: list[BidItem] = Field(max_length=24)


@router.get("/session")
async def get_session() -> dict:
    """현재 입찰 세션 (입찰서·상태·마감 카운트다운)."""
    try:
        return success_response(market_service.get_session())
    except Exception as exc:
        logger.error("market_session_failed", error=str(exc))
        return success_response({"status": "error"})


@router.post("/bids")
async def save_bids(body: BidSheet) -> dict:
    """입찰서 저장 (draft)."""
    try:
        return success_response(
            market_service.save_bids([b.model_dump() for b in body.bids])
        )
    except Exception as exc:
        logger.error("market_save_failed", error=str(exc))
        return success_response({"status": "error"})


@router.post("/submit")
async def submit_bids() -> dict:
    """입찰서 제출."""
    try:
        return success_response(market_service.submit())
    except Exception as exc:
        logger.error("market_submit_failed", error=str(exc))
        return success_response({"status": "error"})


@router.post("/clear")
async def clear_market() -> dict:
    """개찰 (시연용 수동 트리거) — 낙찰 판정 + 예상 정산."""
    try:
        return success_response(market_service.clear())
    except Exception as exc:
        logger.error("market_clear_failed", error=str(exc))
        return success_response({"status": "error"})


@router.get("/mcp-forecast")
async def get_mcp_forecast() -> dict:
    """내일 시장청산가격 예상 곡선 (입찰 참고)."""
    try:
        return success_response({"curve": market_service.mcp_forecast()})
    except Exception as exc:
        logger.error("market_mcp_failed", error=str(exc))
        return success_response({"curve": []})


@router.get("/ai-bids")
async def get_ai_bids() -> dict:
    """학습된 정책 신경망의 추천 입찰 곡선."""
    try:
        forecast = market_service.mcp_forecast()
        return success_response(ai_bids(forecast))
    except Exception as exc:
        logger.error("market_ai_bids_failed", error=str(exc))
        return success_response({"bids": []})


@router.get("/history")
async def get_history() -> dict:
    """과거 입찰 세션 이력."""
    try:
        return success_response({"sessions": market_service.history()})
    except Exception as exc:
        logger.error("market_history_failed", error=str(exc))
        return success_response({"sessions": []})

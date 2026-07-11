"""급전 이행 API — 낙찰 스케줄 이행·RTU 상태·정산."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from app.schemas.response import success_response
from app.services.dispatch_service import dispatch_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/dispatch", tags=["dispatch"])


@router.get("/status")
async def get_status() -> dict:
    """이행 현황 + Mock RTU 하트비트 + 시장 상태머신."""
    try:
        return success_response(dispatch_service.status())
    except Exception as exc:
        logger.error("dispatch_status_failed", error=str(exc))
        return success_response({"active": None})


@router.post("/activate")
async def activate() -> dict:
    """최근 개찰 세션을 이행 스케줄로 활성화 (가속 시연)."""
    try:
        result = dispatch_service.activate_latest_award()
        if result is None:
            return success_response({"error": "개찰된 세션 없음 — 먼저 입찰·개찰 필요"})
        return success_response(result)
    except Exception as exc:
        logger.error("dispatch_activate_failed", error=str(exc))
        return success_response({"error": "활성화 실패"})

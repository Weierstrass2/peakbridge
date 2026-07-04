"""통합 상태 API — AI 의사결정용 15개 변수."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter

from app.core.deps import DbSession
from app.schemas.response import success_response
from app.services.state_collector import state_collector

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/state", tags=["state"])


@router.get("/{building_id}")
async def get_state(session: DbSession, building_id: str) -> dict:
    """GET /api/v1/state/{building_id} — 15개 상태 변수 통합 수집."""
    try:
        state = await state_collector.collect(building_id, session)
    except Exception as exc:
        logger.error("state_collect_failed", building_id=building_id, error=str(exc))
        state = {}
    return success_response(
        {
            "building_id": building_id,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "state": state,
        }
    )

"""차주(EV) 충전 세션 API — 모바일 화면(/drive) + 관제 운영자 조회용.

── 시연 흐름 ──────────────────────────────────────────────────
    1. 차주가 폰으로 QR 접속 → 세션 등록 (POST /drive/session)
    2. 관제(/app 충전기 탭)가 유연성 재고를 조회 (GET /drive/flexibility)
    3. VPP OS 제주 탭이 그 재고를 플러스DR 배분에 반영

로그인 없음 — 세대는 간단한 코드로 식별한다(시연 마찰 제거).
상태는 메모리에만 둔다(서버 재시작 시 초기화).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.schemas.response import success_response
from app.services.flex_service import flex_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/drive", tags=["drive"])


class SessionReq(BaseModel):
    household: str = Field(default="", max_length=20,
                           description="세대 식별 코드 (예: 1203). 로그인 대체")
    need_kwh: float = Field(..., gt=0, le=200,
                            description="출발 전까지 채워야 하는 전력량 (kWh)")
    depart: str = Field(default="", max_length=20,
                        description="출발 시각 표시용 (예: 18:30)")
    mode: str = Field(default="eco",
                      description="eco(알뜰 충전) | now(즉시 충전)")
    building_id: str = Field(default="building-A")


@router.post("/session")
async def create_session(body: SessionReq) -> dict:
    """충전 세션 등록. '알뜰 충전'이면 유연성 재고에 즉시 반영된다."""
    try:
        sess = flex_service.register(
            household=body.household,
            need_kwh=body.need_kwh,
            depart=body.depart,
            mode=body.mode,
            building_id=body.building_id,
        )
        return success_response(sess)
    except Exception as exc:  # noqa: BLE001
        logger.error("drive_create_session_failed", error=str(exc))
        return success_response({"error": str(exc)[:200]})


@router.get("/session/{code}")
async def get_session(code: str) -> dict:
    """세션 단건 조회 — 폰 화면 상태 갱신용."""
    try:
        sess = flex_service.get(code)
        if sess is None:
            return success_response({"error": "세션을 찾을 수 없습니다", "code": code})
        return success_response(sess)
    except Exception as exc:  # noqa: BLE001
        logger.error("drive_get_session_failed", error=str(exc))
        return success_response({"error": str(exc)[:200]})


@router.post("/session/{code}/cancel")
async def cancel_session(code: str) -> dict:
    """세션 취소 — 유연성 재고에서 즉시 빠진다."""
    try:
        sess = flex_service.cancel(code)
        if sess is None:
            return success_response({"error": "세션을 찾을 수 없습니다", "code": code})
        return success_response(sess)
    except Exception as exc:  # noqa: BLE001
        logger.error("drive_cancel_session_failed", error=str(exc))
        return success_response({"error": str(exc)[:200]})


@router.get("/sessions")
async def list_sessions(
    building_id: str | None = None, active_only: bool = False
) -> dict:
    """세션 목록 (관제 운영자용) — 최신순."""
    try:
        rows = flex_service.list_sessions(building_id, active_only)
        return success_response({"sessions": rows, "count": len(rows)})
    except Exception as exc:  # noqa: BLE001
        logger.error("drive_list_sessions_failed", error=str(exc))
        return success_response({"sessions": [], "count": 0})


@router.get("/flexibility")
async def flexibility(building_id: str = "building-A") -> dict:
    """유연성 재고 — 활성 '알뜰 충전' 세션의 필요 전력량 합.

    관제 충전기 탭과 제주 플러스DR 배분이 함께 참조하는 단일 진실원.
    """
    try:
        return success_response(flex_service.flexibility(building_id))
    except Exception as exc:  # noqa: BLE001
        logger.error("drive_flexibility_failed", error=str(exc))
        return success_response({"flex_kwh": 0.0, "flex_session_count": 0,
                                 "sessions": []})


@router.post("/reset")
async def reset() -> dict:
    """세션 전체 초기화 (시연 리허설 반복용)."""
    try:
        return success_response(flex_service.reset())
    except Exception as exc:  # noqa: BLE001
        logger.error("drive_reset_failed", error=str(exc))
        return success_response({"cleared": 0})

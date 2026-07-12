"""전력시장(DAM) 입찰 API — 입찰서 작성·제출·개찰."""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.schemas.response import success_response
from app.services.market_service import market_service
from app.services.ops_service import ops_service
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
        r = market_service.submit()
        ops_service.audit('operator', 'BID_SUBMIT', f"세션 {r.get('session_id')} 입찰 제출")
        return success_response(r)
    except Exception as exc:
        logger.error("market_submit_failed", error=str(exc))
        return success_response({"status": "error"})


@router.post("/clear")
async def clear_market() -> dict:
    """개찰 (시연용 수동 트리거) — 낙찰 판정 + 예상 정산."""
    try:
        r = market_service.clear()
        res = r.get('results') or {}
        ops_service.audit('operator', 'MARKET_CLEAR', f"세션 {r.get('session_id')} 개찰 — {res.get('awarded_hours')}구간 낙찰")
        ops_service.alarm('INFO', 'market', f"개찰 완료 — 낙찰 {res.get('awarded_hours')}구간, 예상 ₩{int(res.get('total_expected_revenue', 0)):,}")
        return success_response(r)
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


# ── 실시간 시장 (RT, 15분 슬롯) — A1+d ─────────────────────

from datetime import datetime, timedelta, timezone as _tz

_KST = _tz(timedelta(hours=9))


def _rt_slot() -> dict:
    """현재 15분 슬롯 정보 + RT 가격 (DAM MCP 기반 ± 실시간 변동)."""
    import math
    import random as _r
    now = datetime.now(_KST)
    slot_idx = now.hour * 4 + now.minute // 15
    slot_start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    slot_end = slot_start + timedelta(minutes=15)
    base = market_service.mcp_forecast()[now.hour]
    rng = _r.Random(now.toordinal() * 100 + slot_idx)
    rt_price = round(base * (1.0 + rng.uniform(-0.12, 0.18)) *
                     (1.05 + 0.05 * math.sin(slot_idx / 96 * 6.28)), 1)
    return {
        "slot": f"{slot_start.strftime('%H:%M')}~{slot_end.strftime('%H:%M')}",
        "seconds_left": int((slot_end - now).total_seconds()),
        "rt_price": rt_price,
        "dam_ref": round(base, 1),
    }


@router.get("/rt")
async def get_rt_market() -> dict:
    """실시간 시장 현재 슬롯 (15분) — RT 가격, 마감 카운트다운."""
    try:
        return success_response(_rt_slot())
    except Exception as exc:
        logger.error("market_rt_failed", error=str(exc))
        return success_response({"slot": "--", "seconds_left": 0, "rt_price": 0, "dam_ref": 0})


class RtSellRequest(BaseModel):
    qty_kw: float = Field(gt=0, le=500)


@router.post("/rt/sell")
async def rt_sell(body: RtSellRequest) -> dict:
    """RT 즉시 판매 — 현재 슬롯 가격 97%(시장가 주문 슬리피지)로 체결."""
    try:
        from app.core.resources import total_max_discharge_kw
        from app.services.vpp_ledger import vpp_ledger

        slot = _rt_slot()
        qty = min(body.qty_kw, total_max_discharge_kw())
        fill = round(slot["rt_price"] * 0.97, 1)
        kwh = round(qty * 0.25, 1)          # 15분 슬롯 = 0.25h
        revenue = round(kwh * fill, 0)
        vpp_ledger.record(
            "RT판매",
            f"실시간 {slot['slot']} — {qty:.0f}kW×15분 @₩{fill}",
            kwh, revenue,
        )
        ops_service.audit("operator", "RT_SELL", f"{slot['slot']} {qty:.0f}kW 체결 ₩{int(revenue):,}")
        return success_response(
            {"filled": True, "slot": slot["slot"], "qty_kw": qty,
             "fill_price": fill, "kwh": kwh, "revenue": revenue}
        )
    except Exception as exc:
        logger.error("market_rt_sell_failed", error=str(exc))
        return success_response({"filled": False})

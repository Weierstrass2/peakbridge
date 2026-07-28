"""트레이딩 데스크 API — 블로터·리스크·손익분해·체결품질·예측품질.

실제 데스크 화면이 호출하는 엔드포인트 묶음이다.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.schemas.response import success_response
from app.services.market_service import market_service
from app.services.strategy_service import strategy_service
from app.services.trading.desk import trading_desk

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/desk", tags=["desk"])


@router.get("/overview")
async def overview() -> dict:
    """데스크 헤더 — 자산·손익·리스크 한눈에."""
    try:
        risk = trading_desk.risk_view()
        pnl = trading_desk.pnl_view()
        return success_response({
            "portfolio": risk["portfolio"],
            "equity_won": risk.get("equity_won", 0),
            "sessions": risk["sessions"],
            "current_sharpe": risk.get("current_sharpe"),
            "current_drawdown_won": risk.get("current_drawdown_won", 0),
            "var95_won": risk["var95_won"],
            "cvar95_won": risk["cvar95_won"],
            "kill_switch": risk["kill_switch"],
            "reason": risk["reason"],
            "active_strategy": strategy_service.active,
            "totals": pnl.get("totals", {}),
        })
    except Exception as exc:  # noqa: BLE001
        logger.error("desk_overview_failed", error=str(exc))
        return success_response({})


@router.get("/blotter")
async def blotter(limit: int = 60) -> dict:
    """체결 블로터 — 최신순 체결 내역."""
    try:
        return success_response({"fills": trading_desk.blotter_view(limit)})
    except Exception as exc:  # noqa: BLE001
        logger.error("desk_blotter_failed", error=str(exc))
        return success_response({"fills": []})


@router.get("/pnl")
async def pnl() -> dict:
    """손익 분해 + 롤링 지표."""
    try:
        return success_response(trading_desk.pnl_view())
    except Exception as exc:  # noqa: BLE001
        logger.error("desk_pnl_failed", error=str(exc))
        return success_response({"sessions": []})


@router.get("/tca")
async def tca() -> dict:
    """체결 품질 (슬리피지·기회손실)."""
    try:
        return success_response(trading_desk.tca_view())
    except Exception as exc:  # noqa: BLE001
        logger.error("desk_tca_failed", error=str(exc))
        return success_response({})


@router.get("/forecast-quality")
async def fq() -> dict:
    """예측 품질 (MAPE·pinball·캘리브레이션)."""
    try:
        return success_response(trading_desk.forecast_view())
    except Exception as exc:  # noqa: BLE001
        logger.error("desk_fq_failed", error=str(exc))
        return success_response({})


@router.get("/risk")
async def risk() -> dict:
    """리스크 상태 + 한도."""
    try:
        return success_response(trading_desk.risk_view())
    except Exception as exc:  # noqa: BLE001
        logger.error("desk_risk_failed", error=str(exc))
        return success_response({})


@router.get("/pre-trade")
async def pre_trade(strategy: str | None = None) -> dict:
    """제출 전 리스크 심사 — 현재 전략의 입찰안을 검사하고 스트레스까지 계산."""
    try:
        forecast = market_service.mcp_forecast()
        plan = strategy_service.build_bids(forecast, strategy=strategy)
        check = trading_desk.pre_trade_check(plan["bids"], forecast)
        check["strategy"] = plan["strategy"]
        check["bids"] = plan["bids"]
        return success_response(check)
    except Exception as exc:  # noqa: BLE001
        logger.error("desk_pretrade_failed", error=str(exc))
        return success_response({"blocked": False, "checks": []})


class SeedRequest(BaseModel):
    strategy: str = Field(default="zscore")
    days: int = Field(default=30, ge=5, le=120)


@router.post("/seed")
async def seed(body: SeedRequest) -> dict:
    """과거 실데이터로 데스크 채우기 (시연 시작 전 1회)."""
    try:
        return success_response(trading_desk.seed_from_backtest(body.strategy, body.days))
    except Exception as exc:  # noqa: BLE001
        logger.error("desk_seed_failed", error=str(exc))
        return success_response({"seeded": 0})


@router.post("/kill-switch/reset")
async def reset_kill() -> dict:
    """킬스위치 해제 — 리스크 검토 후 거래 재개."""
    trading_desk.risk.reset()
    logger.info("desk_kill_switch_reset")
    return success_response({"kill_switch": False})


@router.post("/reset")
async def reset() -> dict:
    """데스크 초기화 (블로터·세션·킬스위치)."""
    return success_response(trading_desk.reset())

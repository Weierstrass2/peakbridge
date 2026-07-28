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
from app.services.trading.hedge import hedged_pnl, plan_hedge
from app.services.trading.settlement import own_settlement, reconcile, simulate_statement

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


@router.get("/hedge")
async def hedge(strategy: str | None = None, available_ratio: float = 0.7) -> dict:
    """실시간시장 헤지 계획 — 부족분을 RT에서 되사는 편이 유리한지 구간별로 판단.

    available_ratio: 급전 시점 가용 에너지 비율 (시연용 시나리오 조절)
    """
    try:
        mcp = market_service.mcp_forecast()
        plan_bids = strategy_service.build_bids(mcp, strategy=strategy)
        awarded = [b for b in plan_bids["bids"] if b["qty_kw"] > 0 and b["price"] <= mcp[b["hour"]]]
        available = plan_bids["usable_kwh"] * max(0.0, min(1.5, available_ratio))

        plan = plan_hedge(awarded, available, mcp)

        # 헤지 없이 위약금을 전부 문 경우의 손익 = 비교 기준선
        from app.services.trading.analytics import attribute_pnl

        attr = attribute_pnl(plan_bids["bids"], mcp, mcp, available)
        comparison = hedged_pnl(attr["net_won"], plan)
        return success_response({
            "strategy": plan_bids["strategy"],
            "available_kwh": round(available, 1),
            "available_ratio": available_ratio,
            **plan,
            "comparison": comparison,
        })
    except Exception as exc:  # noqa: BLE001
        logger.error("desk_hedge_failed", error=str(exc))
        return success_response({"decisions": [], "summary": {}})


@router.get("/stochastic")
async def stochastic(scenarios: int = 200) -> dict:
    """확률적 입찰 진단 — 시나리오 분포에서의 기대손익·CVaR·손실확률."""
    try:
        from app.services.strategies.base import MarketContext
        from app.services.strategies.stochastic import StochasticCVaR
        from app.core.resources import MARKET_RULES, ess_resources

        mcp = market_service.mcp_forecast()
        res = ess_resources()
        power = sum(r["max_discharge_kw"] for r in res.values())
        energy = sum((60.0 - r["soc_min"]) / 100 * r["capacity_kwh"] for r in res.values())
        ctx = MarketContext(
            forecast=mcp, power_kw=power, energy_kwh=energy,
            price_cap=MARKET_RULES["price_cap"], min_unit_kw=MARKET_RULES["min_bid_unit_kw"],
            degradation_won=50.0,
        )
        return success_response(StochasticCVaR(n_scen=max(50, min(500, scenarios))).explain(ctx))
    except Exception as exc:  # noqa: BLE001
        logger.error("desk_stochastic_failed", error=str(exc))
        return success_response({})


@router.get("/settlement")
async def settlement(error_mode: str = "underpay", available_ratio: float = 0.85,
                     strategy: str | None = None) -> dict:
    """정산 검증 — 거래소 정산서 vs 자체 계산 대조.

    error_mode: none | underpay | penalty_over | capacity_miss
                (실연동 전까지 정산서를 시뮬레이션한다)
    """
    try:
        mcp = market_service.mcp_forecast()
        plan = strategy_service.build_bids(mcp, strategy=strategy)
        awarded = [b for b in plan["bids"] if b["qty_kw"] > 0 and b["price"] <= mcp[b["hour"]]]

        # 자체 계측 기록으로 이행량 재구성 (에너지 한도 안에서 순차 이행)
        left = plan["usable_kwh"] * max(0.0, min(1.5, available_ratio))
        delivered: dict[int, float] = {}
        for b in sorted(awarded, key=lambda r: int(r["hour"])):
            d = min(float(b["qty_kw"]), left)
            delivered[int(b["hour"])] = round(d, 2)
            left -= d

        ours = own_settlement(awarded, delivered, mcp)
        theirs = simulate_statement(ours, error_mode=error_mode)
        result = reconcile(ours, theirs)
        return success_response({
            "strategy": plan["strategy"],
            "error_mode": error_mode,
            "ours": ours,
            "theirs": theirs,
            **result,
        })
    except Exception as exc:  # noqa: BLE001
        logger.error("desk_settlement_failed", error=str(exc))
        return success_response({"checks": [], "status": "error"})


@router.get("/overfit")
async def overfit(days: int = 90) -> dict:
    """과최적화 진단 — Deflated Sharpe + PBO.

    전 전략을 같은 기간에 돌려 손익 행렬을 만든 뒤,
    '여러 전략을 시험했다'는 사실 자체를 보정한 유의성을 계산한다.
    """
    try:
        import random as _rnd

        from app.core.resources import MARKET_RULES, ess_resources
        from app.services import market_data
        from app.services.strategies import MarketSimulator, registry, run_backtest
        from app.services.strategies.overfit import deflated_sharpe, pbo

        market_data._load_once()
        pool = sorted({(k[0], k[1], k[2]) for k in market_data._price
                       if k[3] == 12 and k[0] < 2026})
        if not pool:
            return success_response({"error": "가격 데이터 없음"})

        res = ess_resources()
        power = sum(r["max_discharge_kw"] for r in res.values())
        energy = sum((60.0 - r["soc_min"]) / 100 * r["capacity_kwh"] for r in res.values())
        sim = MarketSimulator(
            price_map=market_data._price, dpct_map=market_data._dpct, rules=MARKET_RULES,
            power_kw=power, energy_kwh=energy, degradation_won=50.0,
        )
        sample = sorted(_rnd.Random(999).sample(pool, min(max(30, days), len(pool))))

        matrix: dict[str, list[float]] = {}
        for name, factory in registry().items():
            if name == "stochastic_cvar":
                continue          # 시나리오 최적화는 계산량이 커 진단에서 제외
            r = run_backtest(factory(), sim, sample, seed=999)
            matrix[name] = [d.pnl for d in r.days]

        best = max(matrix, key=lambda k: float(sum(matrix[k]) / len(matrix[k])))
        dsr = deflated_sharpe(matrix[best], n_trials=len(matrix))
        p = pbo(matrix, n_splits=8)
        return success_response({
            "best_strategy": best,
            "test_days": len(sample),
            "deflated_sharpe": dsr,
            "pbo": p,
        })
    except Exception as exc:  # noqa: BLE001
        logger.error("desk_overfit_failed", error=str(exc))
        return success_response({})


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

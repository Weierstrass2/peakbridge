"""트레이딩 데스크 — 블로터·포지션·리스크·애널리틱스 통합 서비스.

실제 데스크의 하루:
    D-1 예측 확인 → 전략 선택 → 사전 리스크 체크 → 제출 → 개찰 →
    실시간 이행 감시 → 마감 후 손익 분해 · 체결품질 리뷰

이 서비스가 그 흐름을 그대로 담는다.

주의: 블로터·포지션은 in-memory(deque)다. 서버 재시작 시 초기화된다
      (시장·이행·원장과 동일한 설계 원칙).
"""

from __future__ import annotations

import random
from collections import deque
from datetime import date, datetime, timedelta, timezone

import structlog

from app.core.resources import MARKET_RULES, ess_resources
from app.services import market_data
from app.services.strategies import MarketSimulator, registry
from app.services.trading.analytics import (
    attribute_pnl,
    forecast_quality,
    rolling_metrics,
    transaction_cost_analysis,
)
from app.services.trading.risk import RiskEngine, RiskLimits

logger = structlog.get_logger(__name__)
KST = timezone(timedelta(hours=9))

BLOTTER_MAX = 500
SESSION_MAX = 120
DEFAULT_SOC = 60.0


class TradingDesk:
    def __init__(self) -> None:
        self.risk = RiskEngine(RiskLimits())
        self.blotter: deque[dict] = deque(maxlen=BLOTTER_MAX)   # 체결 단위 기록
        self.sessions: deque[dict] = deque(maxlen=SESSION_MAX)  # 일 단위 기록
        self._fc_hist: list[list[float]] = []
        self._ac_hist: list[list[float]] = []
        self._seq = 0

    # ── 포트폴리오 ──
    def portfolio(self, soc: dict[str, float] | None = None) -> dict:
        res = ess_resources()
        power = sum(r["max_discharge_kw"] for r in res.values())
        energy = sum(
            max(0.0, (soc or {}).get(k, DEFAULT_SOC) - r["soc_min"]) / 100 * r["capacity_kwh"]
            for k, r in res.items()
        )
        return {"power_kw": power, "usable_kwh": round(energy, 1), "units": len(res)}

    # ── 사전 리스크 체크 ──
    def pre_trade_check(self, bids: list[dict], mcp_forecast: list[float],
                        soc: dict[str, float] | None = None) -> dict:
        pf = self.portfolio(soc)
        pnl_hist = [s["net_won"] for s in self.sessions]
        var95, cvar95 = RiskEngine.var_cvar(pnl_hist)
        roll = rolling_metrics(pnl_hist) if pnl_hist else {"current_drawdown": 0}
        today = self.sessions[-1]["net_won"] if self.sessions else 0.0

        state = self.risk.pre_trade(
            bids=bids,
            mcp_forecast=mcp_forecast,
            usable_kwh=pf["usable_kwh"],
            realized_pnl_today=today,
            drawdown=abs(roll.get("current_drawdown", 0) or 0),
            var95=var95,
        )
        out = state.to_dict()
        out["var95_won"] = round(var95)
        out["cvar95_won"] = round(cvar95)
        out["stress"] = RiskEngine.stress(bids, mcp_forecast, pf["usable_kwh"])
        out["portfolio"] = pf
        return out

    # ── 체결 기록 ──
    def record_session(self, strategy: str, bids: list[dict], mcp_actual: list[float],
                       mcp_forecast: list[float], soc: dict[str, float] | None = None,
                       day: str | None = None) -> dict:
        """개찰 결과를 데스크에 반영한다 (손익 분해 + 블로터 기록 + 킬스위치 판정)."""
        pf = self.portfolio(soc)
        attr = attribute_pnl(bids, mcp_actual, mcp_forecast, pf["usable_kwh"])
        tca = transaction_cost_analysis(bids, mcp_actual)

        ts = day or datetime.now(KST).strftime("%Y-%m-%d")
        energy_left = pf["usable_kwh"]
        for row in tca["rows"]:
            if not row["awarded"]:
                continue
            self._seq += 1
            delivered = min(row["qty_kw"], energy_left)
            energy_left -= delivered
            self.blotter.appendleft({
                "id": f"F{self._seq:05d}",
                "date": ts,
                "hour": row["hour"],
                "strategy": strategy,
                "side": "SELL",
                "qty_kw": row["qty_kw"],
                "delivered_kw": round(delivered, 1),
                "bid_price": row["bid_price"],
                "clear_price": row["mcp"],
                "slippage": row["slippage"],
                "value_won": row["value_won"],
                "status": "이행" if delivered >= row["qty_kw"] - 0.5 else "부분이행",
            })

        session = {
            "date": ts,
            "strategy": strategy,
            "net_won": attr["net_won"],
            "attribution": attr["components"],
            "volume": attr["volume"],
            "tca": {k: v for k, v in tca.items() if k != "rows"},
        }
        self.sessions.append(session)
        self._fc_hist.append(list(mcp_forecast))
        self._ac_hist.append(list(mcp_actual))

        # 킬스위치 — 손실 한도 초과 시 자동 거래 중지
        L = self.risk.limits
        if attr["net_won"] < -L.max_daily_loss_won:
            self.risk.trip(f"일 손실 한도 초과 (₩{attr['net_won']:,} < -₩{L.max_daily_loss_won:,.0f})")
            logger.warning("desk_kill_switch", reason=self.risk._kill_reason)
        roll = rolling_metrics([s["net_won"] for s in self.sessions])
        if abs(roll.get("current_drawdown", 0) or 0) > L.max_drawdown_won:
            self.risk.trip(f"드로다운 한도 초과 (₩{roll['current_drawdown']:,})")

        return session

    # ── 조회 ──
    def blotter_view(self, limit: int = 60) -> list[dict]:
        return list(self.blotter)[:limit]

    def pnl_view(self) -> dict:
        if not self.sessions:
            return {"sessions": [], "totals": {}, "rolling": {"points": []}}
        pnl = [s["net_won"] for s in self.sessions]
        keys = ["base_revenue", "price_effect", "capacity_payment", "degradation", "penalty"]
        totals = {k: sum(s["attribution"].get(k, 0) for s in self.sessions) for k in keys}
        totals["net"] = sum(pnl)
        return {
            "sessions": list(self.sessions)[-30:],
            "totals": totals,
            "rolling": rolling_metrics(pnl),
        }

    def tca_view(self) -> dict:
        if not self.sessions:
            return {}
        agg = [s["tca"] for s in self.sessions]
        n = len(agg)
        return {
            "avg_slippage": round(sum(a["avg_slippage"] for a in agg) / n, 2),
            "hit_ratio": round(sum(a["hit_ratio"] or 0 for a in agg) / n, 3),
            "captured_won": sum(a["captured_won"] for a in agg),
            "missed_value_won": sum(a["missed_value_won"] for a in agg),
            "sessions": n,
        }

    def forecast_view(self) -> dict:
        return forecast_quality(self._fc_hist, self._ac_hist)

    def risk_view(self, mcp_forecast: list[float] | None = None,
                  soc: dict[str, float] | None = None) -> dict:
        pnl = [s["net_won"] for s in self.sessions]
        var95, cvar95 = RiskEngine.var_cvar(pnl)
        roll = rolling_metrics(pnl) if pnl else {}
        return {
            "limits": self.risk.limits.__dict__,
            "kill_switch": self.risk.kill_switch,
            "reason": self.risk._kill_reason,
            "var95_won": round(var95),
            "cvar95_won": round(cvar95),
            "current_drawdown_won": roll.get("current_drawdown", 0),
            "current_sharpe": roll.get("current_sharpe"),
            "equity_won": roll.get("equity_won", 0),
            "sessions": len(self.sessions),
            "portfolio": self.portfolio(soc),
        }

    # ── 시연용 시딩 ──
    def seed_from_backtest(self, strategy: str = "zscore", days: int = 30,
                           seed: int = 4242) -> dict:
        """과거 실데이터로 데스크를 채운다 — 시연 시작 시 빈 화면 방지.

        백테스트와 같은 시장 엔진을 쓰므로 숫자가 서로 어긋나지 않는다.
        """
        market_data._load_once()
        pool = sorted({(k[0], k[1], k[2]) for k in market_data._price if k[3] == 12 and k[0] < 2026})
        if not pool:
            return {"seeded": 0}
        pf = self.portfolio()
        sim = MarketSimulator(
            price_map=market_data._price, dpct_map=market_data._dpct, rules=MARKET_RULES,
            power_kw=pf["power_kw"], energy_kwh=pf["usable_kwh"], degradation_won=50.0,
        )
        factory = registry().get(strategy) or registry()["greedy_budget"]
        strat = factory()
        rng = random.Random(seed)
        chosen = sorted(random.Random(seed).sample(pool, min(days, len(pool))))

        self.blotter.clear(); self.sessions.clear()
        self._fc_hist.clear(); self._ac_hist.clear()
        self.risk.reset()

        for (y, m, d) in chosen:
            actual = sim.curve(y, m, d, 1.0, rng)
            fc = sim.forecast_curve(actual, rng)
            bids = [
                {"hour": b.hour, "qty_kw": b.qty_kw, "price": b.price}
                for b in strat.bids(sim.context(fc, []))
            ]
            self.record_session(strategy, bids, actual, fc, day=f"{y}-{m:02d}-{d:02d}")
        logger.info("desk_seeded", strategy=strategy, days=len(chosen), fills=len(self.blotter))
        return {"seeded": len(chosen), "fills": len(self.blotter), "strategy": strategy}

    def reset(self) -> dict:
        self.blotter.clear(); self.sessions.clear()
        self._fc_hist.clear(); self._ac_hist.clear()
        self.risk.reset()
        return {"reset": True}


trading_desk = TradingDesk()

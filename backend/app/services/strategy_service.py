"""전략 운영 서비스 — 벤치마크 결과 서빙 + 활성 전략 관리.

퀀트 운용과 같은 구조다: 오프라인에서 백테스트로 후보를 고르고(benchmark),
운영에서는 선택된 전략이 매일 입찰을 만든다(active strategy).

주의: 활성 전략 선택은 in-memory다 — 서버 재시작 시 기본값으로 돌아간다
      (시장·이행·원장과 동일한 설계).
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from app.core.resources import MARKET_RULES, ess_resources
from app.services.strategies import MarketContext, registry

logger = structlog.get_logger(__name__)

BENCH_PATH = Path(__file__).resolve().parents[2] / "models" / "strategy_benchmark.json"
DEFAULT_STRATEGY = "greedy_budget"


class StrategyService:
    def __init__(self) -> None:
        self._active = DEFAULT_STRATEGY
        self._bench: dict | None = None
        self._instances: dict = {}

    # ── 벤치마크 ──
    def leaderboard(self) -> dict:
        """저장된 백테스트 결과. 없으면 빈 리더보드."""
        if self._bench is None:
            try:
                self._bench = json.load(open(BENCH_PATH, encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("strategy_benchmark_missing", error=str(exc))
                self._bench = {"leaderboard": [], "test_days": 0}
        return self._bench

    def reload(self) -> dict:
        self._bench = None
        return self.leaderboard()

    # ── 전략 목록·선택 ──
    def catalog(self) -> list[dict]:
        out = []
        bench = {r["name"]: r for r in self.leaderboard().get("leaderboard", [])}
        for name, factory in registry().items():
            inst = self._instances.get(name) or factory()
            self._instances[name] = inst
            b = bench.get(name, {})
            out.append({
                "name": name,
                "family": getattr(inst, "family", "unknown"),
                "description": getattr(inst, "description", ""),
                "active": name == self._active,
                "daily_mean_won": b.get("daily_mean_won"),
                "sharpe": b.get("sharpe"),
                "max_drawdown_won": b.get("max_drawdown_won"),
                "hit_rate": b.get("hit_rate"),
                "fill_rate": b.get("fill_rate"),
            })
        out.sort(key=lambda r: (r["daily_mean_won"] is None, -(r["daily_mean_won"] or 0)))
        return out

    @property
    def active(self) -> str:
        return self._active

    def set_active(self, name: str) -> dict:
        if name not in registry():
            raise ValueError(f"알 수 없는 전략입니다: {name}")
        self._active = name
        logger.info("strategy_activated", strategy=name)
        return {"active": name}

    # ── 운영 입찰 생성 ──
    def build_bids(self, forecast: list[float], soc: dict[str, float] | None = None,
                   strategy: str | None = None) -> dict:
        """활성(또는 지정) 전략으로 24구간 입찰을 만든다."""
        name = strategy or self._active
        factory = registry().get(name)
        if factory is None:
            raise ValueError(f"알 수 없는 전략입니다: {name}")
        inst = self._instances.get(name) or factory()
        self._instances[name] = inst

        res = ess_resources()
        power = sum(r["max_discharge_kw"] for r in res.values())
        energy = sum(
            max(0.0, (soc or {}).get(k, 60.0) - r["soc_min"]) / 100 * r["capacity_kwh"]
            for k, r in res.items()
        )
        ctx = MarketContext(
            forecast=forecast,
            power_kw=power,
            energy_kwh=energy,
            price_cap=MARKET_RULES["price_cap"],
            min_unit_kw=MARKET_RULES["min_bid_unit_kw"],
            degradation_won=50.0,
        )
        bids = inst.bids(ctx)
        bench = {r["name"]: r for r in self.leaderboard().get("leaderboard", [])}.get(name, {})
        return {
            "strategy": name,
            "family": getattr(inst, "family", "unknown"),
            "description": getattr(inst, "description", ""),
            "backtest": {
                "daily_mean_won": bench.get("daily_mean_won"),
                "sharpe": bench.get("sharpe"),
                "max_drawdown_won": bench.get("max_drawdown_won"),
                "test_days": self.leaderboard().get("test_days"),
            },
            "usable_kwh": round(energy, 1),
            "power_kw": power,
            "bids": [{"hour": b.hour, "qty_kw": b.qty_kw, "price": b.price} for b in bids],
        }


strategy_service = StrategyService()

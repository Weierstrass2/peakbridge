"""VPP 입찰 전략 백테스트 엔진 — 퀀트 성과평가 지표를 그대로 적용.

시장 시뮬레이션 규칙 (market_service.clear()와 동일한 문법):
  1. 입찰가 ≤ 실현 MCP 이면 낙찰 (pay-as-clear — 실현 MCP로 정산)
  2. 낙찰량은 남은 에너지 한도 안에서만 이행 가능
  3. 이행하지 못한 부족분은 위약금 = 부족분 × MCP × penalty_factor
  4. 방전 에너지에는 배터리 열화비용이 차감된다
  5. 신고 용량에는 용량요금(CP)이 지급된다

편향 방지 장치:
  - 전략은 예측 곡선만 본다. 실현 MCP는 정산 단계에서만 등장한다
  - 워크포워드: 학습·튜닝 구간과 검증 구간을 시간순으로 분리한다
  - 온라인 전략(bandit)은 '어제까지의 실현 손익'만 받는다
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from .base import Bid, MarketContext

HOURS = 24
TRADING_DAYS = 365  # 전력시장은 연중무휴 → 연율화 기준일


@dataclass
class DayResult:
    day: tuple[int, int, int]
    pnl: float
    revenue: float
    capacity_payment: float
    penalty: float
    degradation: float
    awarded_kwh: float
    delivered_kwh: float
    bid_kwh: float

    @property
    def fill_rate(self) -> float:
        return self.delivered_kwh / self.awarded_kwh if self.awarded_kwh > 0 else 1.0


@dataclass
class BacktestResult:
    strategy: str
    family: str
    description: str
    days: list[DayResult] = field(default_factory=list)

    @property
    def pnl(self) -> np.ndarray:
        return np.asarray([d.pnl for d in self.days], dtype=float)

    def metrics(self) -> dict:
        p = self.pnl
        if len(p) == 0:
            return {}
        mean = float(p.mean())
        sd = float(p.std(ddof=1)) if len(p) > 1 else 0.0
        downside = p[p < 0]
        dsd = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0

        equity = np.cumsum(p)                     # 누적 손익 곡선
        peak = np.maximum.accumulate(equity)
        drawdown = equity - peak
        mdd = float(-drawdown.min()) if len(drawdown) else 0.0

        srt = np.sort(p)
        var5 = float(srt[max(0, int(len(srt) * 0.05) - 1)])
        cvar5 = float(srt[: max(1, int(len(srt) * 0.05))].mean())

        awarded = sum(d.awarded_kwh for d in self.days)
        delivered = sum(d.delivered_kwh for d in self.days)
        bid = sum(d.bid_kwh for d in self.days)

        return {
            # 수익성
            "daily_mean_won": round(mean),
            "annual_won": round(mean * TRADING_DAYS),
            "total_won": round(float(p.sum())),
            # 위험조정 (일단위 → 연율화)
            "sharpe": round(mean / sd * math.sqrt(TRADING_DAYS), 2) if sd > 0 else None,
            "sortino": round(mean / dsd * math.sqrt(TRADING_DAYS), 2) if dsd > 0 else None,
            "calmar": round(mean * TRADING_DAYS / mdd, 2) if mdd > 0 else None,
            # 위험
            "volatility_won": round(sd),
            "max_drawdown_won": round(mdd),
            "var5_won": round(var5),
            "cvar5_won": round(cvar5),
            "worst_day_won": round(float(p.min())),
            # 거래 품질
            "hit_rate": round(float((p > 0).mean()), 3),
            "profit_factor": round(
                float(p[p > 0].sum() / abs(p[p < 0].sum())), 2
            ) if (p < 0).any() and (p > 0).any() else None,
            "fill_rate": round(delivered / awarded, 3) if awarded > 0 else None,
            "award_rate": round(awarded / bid, 3) if bid > 0 else None,
            "penalty_won": round(sum(d.penalty for d in self.days)),
            "penalty_share": round(
                sum(d.penalty for d in self.days) / max(sum(d.revenue for d in self.days), 1e-9), 3
            ),
            "utilization": round(delivered / (len(self.days) * 1.0), 1),  # 일평균 방전 kWh
            "days": len(self.days),
        }


class MarketSimulator:
    """가격 생성 + 정산. 예측 곡선과 실현 곡선을 분리해 제공한다."""

    def __init__(self, price_map: dict, dpct_map: dict, rules: dict,
                 power_kw: float, energy_kwh: float, degradation_won: float = 50.0,
                 forecast_error: float = 0.10, error_rho: float = 0.7,
                 energy_uncertainty: float = 0.25) -> None:
        self._price, self._dpct = price_map, dpct_map
        self.rules = rules
        self.power_kw = power_kw
        self.energy_kwh = energy_kwh
        self.degradation_won = degradation_won
        # 하루 전 예측 오차 (표준편차 비율). 0으로 두면 '예측=정답'이 되어
        # 문제가 지나치게 쉬워지고 Sharpe가 비현실적으로 부풀려진다.
        self.forecast_error = forecast_error
        self.error_rho = error_rho  # 시간 간 오차 자기상관 (실제 예측 오차는 뭉쳐서 발생)
        # 가용 에너지 불확실성. 입찰 시점(D-1)의 SOC 예상과 실제 급전 시점의 가용량은 다르다.
        # (자가소비 증가, 충전 실패, 온도에 따른 가용용량 축소 등)
        # 이 항이 없으면 이행 리스크가 사라져 Sharpe가 비현실적으로 부풀려진다.
        self.energy_uncertainty = energy_uncertainty

    def realized_energy(self, rng: random.Random) -> float:
        """급전 시점에 실제로 낼 수 있는 에너지 (계획 대비 축소/확대)."""
        if self.energy_uncertainty <= 0:
            return self.energy_kwh
        factor = rng.gauss(1.0, self.energy_uncertainty)
        return max(0.0, self.energy_kwh * min(1.3, factor))

    def curve(self, y: int, m: int, d: int, jitter: float, rng: random.Random) -> list[float]:
        out = []
        for h in range(HOURS):
            base = self._price.get((y, m, d, h), 84.5)
            pct = self._dpct.get((y, m, d, h), 0.5)
            out.append(base * (0.95 + 0.55 * pct ** 2) * (1 + rng.uniform(-0.03, 0.03) * jitter))
        return out

    def forecast_curve(self, actual: list[float], rng: random.Random) -> list[float]:
        """실현 곡선으로부터 '하루 전 예측'을 생성한다.

        AR(1) 오차를 곱해 시간적으로 뭉치는 예측 오차를 재현한다.
        여기에 하루 전체의 수준을 잘못 보는 편향(level bias)도 더한다 —
        실제 예측이 틀리는 방식과 가깝다.
        """
        if self.forecast_error <= 0:
            return list(actual)
        level_bias = rng.gauss(0.0, self.forecast_error * 0.5)
        e = rng.gauss(0.0, self.forecast_error)
        out = []
        for h in range(HOURS):
            e = self.error_rho * e + math.sqrt(1 - self.error_rho ** 2) * rng.gauss(0.0, self.forecast_error)
            out.append(max(1.0, actual[h] * (1 + e + level_bias)))
        return out

    def context(self, forecast: list[float], history: list[dict]) -> MarketContext:
        return MarketContext(
            forecast=forecast,
            power_kw=self.power_kw,
            energy_kwh=self.energy_kwh,
            price_cap=self.rules["price_cap"],
            min_unit_kw=self.rules["min_bid_unit_kw"],
            degradation_won=self.degradation_won,
            history=history,
        )

    def settle(self, bids: list[Bid], actual: list[float], day: tuple[int, int, int],
               energy_available: float | None = None) -> DayResult:
        """개찰 → 이행 → 정산. market_service.clear()와 같은 규칙."""
        cp_rate = self.rules["cp_rate"]
        pen_factor = self.rules["penalty_factor"]

        energy = self.energy_kwh if energy_available is None else energy_available
        revenue = capacity = penalty = degradation = 0.0
        awarded = delivered = bid_total = 0.0

        for b in bids:
            if b.qty_kw <= 0:
                continue
            bid_total += b.qty_kw
            capacity += b.qty_kw * cp_rate      # 신고 용량에 지급되는 용량요금
            if b.price > actual[b.hour]:
                continue                        # 미낙찰
            awarded += b.qty_kw
            deliv = min(b.qty_kw, energy)       # 1시간 급전 → kW ≈ kWh
            energy -= deliv
            delivered += deliv
            revenue += deliv * actual[b.hour]
            degradation += deliv * self.degradation_won
            short = b.qty_kw - deliv
            if short > 0.5:
                penalty += short * actual[b.hour] * pen_factor

        pnl = revenue - degradation + capacity - penalty
        return DayResult(day, pnl, revenue, capacity, penalty, degradation,
                         awarded, delivered, bid_total)


def run_backtest(strategy, sim: MarketSimulator, days: list[tuple[int, int, int]],
                 seed: int = 999) -> BacktestResult:
    """단일 전략 백테스트. 온라인 전략이면 매일 실현 손익을 되먹인다."""
    res = BacktestResult(
        strategy=getattr(strategy, "name", strategy.__class__.__name__),
        family=getattr(strategy, "family", "unknown"),
        description=getattr(strategy, "description", ""),
    )
    if hasattr(strategy, "reset"):
        strategy.reset()

    rng = random.Random(seed)
    history: list[dict] = []
    for (y, m, d) in days:
        actual = sim.curve(y, m, d, 1.0, rng)          # 실현 MCP
        forecast = sim.forecast_curve(actual, rng)     # 하루 전 예측 (오차 포함)
        bids = strategy.bids(sim.context(forecast, history))
        # 계획 시점 예상 에너지로 입찰하고, 실제 가용량은 급전 시점에 드러난다
        available = sim.realized_energy(rng)
        day_res = sim.settle(bids, actual, (y, m, d), energy_available=available)
        res.days.append(day_res)
        history.append({"day": (y, m, d), "pnl": day_res.pnl, "mcp_mean": float(np.mean(actual))})
        if hasattr(strategy, "update"):
            strategy.update(day_res.pnl)          # 어제 결과만 반영 (룩어헤드 없음)
    return res


def split_walk_forward(days: list, n_folds: int = 3, train_ratio: float = 0.6) -> list[tuple[list, list]]:
    """워크포워드 분할 — 시간순으로 학습/검증 구간을 미끄러뜨린다.

    무작위 분할은 미래 정보가 과거로 새는 통로가 되므로 쓰지 않는다.
    """
    days = sorted(days)
    folds = []
    n = len(days)
    block = n // (n_folds + 1)
    for i in range(n_folds):
        train_end = block * (i + 1)
        test_end = min(n, train_end + block)
        train = days[:train_end]
        test = days[train_end:test_end]
        if len(test) >= 5:
            folds.append((train, test))
    if not folds:  # 데이터가 적으면 단일 분할로 대체
        cut = int(n * train_ratio)
        folds = [(days[:cut], days[cut:])]
    return folds


def bootstrap_ci(pnl: np.ndarray, n: int = 2000, alpha: float = 0.05, seed: int = 7) -> tuple[float, float]:
    """일평균 손익의 부트스트랩 신뢰구간 — 우연으로 이긴 것인지 가른다."""
    if len(pnl) < 5:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = rng.choice(pnl, size=(n, len(pnl)), replace=True).mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)

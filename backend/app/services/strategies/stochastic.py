"""확률적 입찰 — 시나리오 기반 최적화 (CVaR 제약).

점 예측 하나로 입찰하는 것은 "예측이 맞다"는 도박이다.
실제 데스크는 가격 시나리오를 여러 개 뽑아 **기대이익을 최대화하되
하위 꼬리(CVaR)가 허용선 아래로 내려가지 않도록** 제약을 건다.

    max  E[PnL(x)]
    s.t. CVaR_5%[PnL(x)] >= -허용손실
         에너지·정격 제약

풀이는 LP 솔버 없이 **좌표 하강(coordinate descent)**으로 한다.
구간을 하나씩 켜보면서 목적함수가 개선되면 채택하는 방식이라
numpy만으로 충분하고, 배포 경량화 원칙(SB3/torch 금지)에 맞는다.

시나리오 생성:
    예측 곡선에 AR(1) 자기상관 오차 + 일 전체 수준 편향을 곱해 만든다.
    백테스트 엔진의 오차 모델과 동일한 구조를 쓰므로 서로 어긋나지 않는다.

가용 에너지도 확률변수로 다룬다 (SOC 예측 오차). 이행 리스크가
전력시장 손실의 주된 원인이므로, 여기에 불확실성을 넣지 않으면
확률적 최적화의 의미가 없다.
"""

from __future__ import annotations

import numpy as np

from .base import Bid, MarketContext, clamp_price, snap

HOURS = 24


def make_scenarios(forecast: list[float], n: int = 200, sigma: float = 0.10,
                   rho: float = 0.7, level_sigma: float = 0.05,
                   seed: int = 17) -> np.ndarray:
    """가격 시나리오 행렬 (n × 24) 생성."""
    rng = np.random.default_rng(seed)
    fc = np.asarray(forecast, dtype=float)
    out = np.empty((n, HOURS))
    for i in range(n):
        level = rng.normal(0.0, level_sigma)
        e = rng.normal(0.0, sigma)
        row = np.empty(HOURS)
        for h in range(HOURS):
            e = rho * e + np.sqrt(1 - rho ** 2) * rng.normal(0.0, sigma)
            row[h] = max(1.0, fc[h] * (1 + e + level))
        out[i] = row
    return out


def make_energy_draws(energy_kwh: float, n: int, sigma: float = 0.25,
                      seed: int = 23) -> np.ndarray:
    """급전 시점 가용 에너지 시나리오 (계획 대비 편차)."""
    rng = np.random.default_rng(seed)
    return np.clip(rng.normal(1.0, sigma, n), 0.05, 1.3) * energy_kwh


def evaluate(qty: np.ndarray, price: np.ndarray, scen: np.ndarray, energies: np.ndarray,
             degradation: float, cp_rate: float, penalty_factor: float) -> np.ndarray:
    """시나리오별 손익 벡터 (길이 n). 백테스트 정산 규칙과 동일."""
    n = scen.shape[0]
    pnl = np.zeros(n)
    order = np.argsort(price)          # 낙찰 가능성이 높은(싼) 구간부터 에너지 배정
    cp = float(qty.sum()) * cp_rate    # 용량요금은 낙찰과 무관
    for i in range(n):
        mcp = scen[i]
        left = energies[i]
        rev = pen = deg = 0.0
        for h in order:
            q = qty[h]
            if q <= 0 or price[h] > mcp[h]:
                continue
            d = min(q, left)
            left -= d
            rev += d * mcp[h]
            deg += d * degradation
            short = q - d
            if short > 0.5:
                pen += short * mcp[h] * penalty_factor
        pnl[i] = rev - deg + cp - pen
    return pnl


def cvar(pnl: np.ndarray, alpha: float = 0.05) -> float:
    k = max(1, int(len(pnl) * alpha))
    return float(np.sort(pnl)[:k].mean())


class StochasticCVaR:
    """시나리오 기반 CVaR 제약 최적화 전략.

    목적함수 = 기대손익 + λ × min(0, CVaR − 허용손실)
    (CVaR이 허용선 위에 있으면 벌점 없음, 아래로 내려가면 강하게 벌점)

    좌표 하강으로 구간별 (물량, 가격배수)를 순차 개선한다.
    """

    name = "stochastic_cvar"
    family = "stochastic"
    description = "가격·가용에너지 시나리오 200개 · 기대이익 최대화 + CVaR 5% 제약"

    def __init__(self, n_scen: int = 200, alpha: float = 0.05,
                 cvar_floor_ratio: float = -0.5, lam: float = 3.0,
                 price_levels: tuple[float, ...] = (0.80, 0.88, 0.94, 1.0),
                 seed: int = 17) -> None:
        self.n_scen = n_scen
        self.alpha = alpha
        # 허용 CVaR = -(가용에너지 × 평균가 × 비율). 하루 최대 손실 허용선.
        self.cvar_floor_ratio = cvar_floor_ratio
        self.lam = lam
        self.price_levels = price_levels
        self.seed = seed

    def bids(self, ctx: MarketContext) -> list[Bid]:
        fc = ctx.fc
        scen = make_scenarios(list(fc), n=self.n_scen, seed=self.seed)
        energies = make_energy_draws(ctx.energy_kwh, self.n_scen, seed=self.seed + 1)
        cp_rate = 8.0
        pen = 1.2

        floor = self.cvar_floor_ratio * ctx.energy_kwh * float(fc.mean())

        qty = np.zeros(HOURS)
        pmul = np.full(HOURS, 0.94)
        price = np.minimum(fc * pmul, ctx.price_cap)

        def objective(q: np.ndarray, p: np.ndarray) -> tuple[float, float, float]:
            pnl = evaluate(q, p, scen, energies, ctx.degradation_won, cp_rate, pen)
            ev = float(pnl.mean())
            cv = cvar(pnl, self.alpha)
            score = ev + self.lam * min(0.0, cv - floor)
            return score, ev, cv

        best_score, _, _ = objective(qty, price)

        # 기대 마진이 큰 구간부터 후보로 검토 (탐색 비용 절감)
        candidates = list(np.argsort(-(fc - ctx.degradation_won)))
        step = max(ctx.min_unit_kw, ctx.power_kw / 4)

        for h in candidates:
            h = int(h)
            improved = True
            while improved:
                improved = False
                for lvl in self.price_levels:
                    for dq in (step, -step):
                        cand_q = qty.copy()
                        cand_q[h] = float(np.clip(cand_q[h] + dq, 0.0, ctx.power_kw))
                        cand_q[h] = snap(cand_q[h], ctx.min_unit_kw)
                        cand_p = price.copy()
                        cand_p[h] = min(fc[h] * lvl, ctx.price_cap)
                        sc, _, _ = objective(cand_q, cand_p)
                        if sc > best_score + 1.0:     # 유의미한 개선만 채택
                            qty, price, best_score = cand_q, cand_p, sc
                            improved = True

        return [
            Bid(h, float(qty[h]), clamp_price(float(price[h]), ctx.price_cap))
            for h in range(HOURS)
        ]

    def explain(self, ctx: MarketContext) -> dict:
        """이 입찰이 왜 이렇게 나왔는지 — 화면 설명용 진단."""
        bids = self.bids(ctx)
        q = np.array([b.qty_kw for b in bids])
        p = np.array([b.price for b in bids])
        scen = make_scenarios(list(ctx.fc), n=self.n_scen, seed=self.seed)
        energies = make_energy_draws(ctx.energy_kwh, self.n_scen, seed=self.seed + 1)
        pnl = evaluate(q, p, scen, energies, ctx.degradation_won, 8.0, 1.2)
        return {
            "scenarios": self.n_scen,
            "expected_won": round(float(pnl.mean())),
            "cvar5_won": round(cvar(pnl, self.alpha)),
            "var5_won": round(float(np.sort(pnl)[max(1, int(len(pnl) * self.alpha)) - 1])),
            "worst_won": round(float(pnl.min())),
            "best_won": round(float(pnl.max())),
            "loss_prob": round(float((pnl < 0).mean()), 3),
            "active_hours": int((q > 0).sum()),
            "bids": [{"hour": b.hour, "qty_kw": b.qty_kw, "price": b.price} for b in bids],
        }

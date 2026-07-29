"""VPP 자동매매 전략 라이브러리.

각 전략은 예측 가격 곡선만 보고 24구간 입찰(수량·가격)을 만든다.
실현 MCP는 절대 참조하지 않는다 (룩어헤드 편향 차단).

계열(family):
    rule        — 사람이 손으로 짤 법한 기준선. 벤치마크 역할
    optimize    — 제약 하 최적화 (에너지 예산 배분)
    statistical — 통계적 신호 (z-score, 변동성, 분위수)
    learned     — 학습된 정책 (CEM 신경망)
    meta        — 다른 전략을 고르거나 섞는 상위 전략
"""

from __future__ import annotations

import math

import numpy as np

from .base import Bid, MarketContext, clamp_price, energy_feasible, snap, var_cost_floor

HOURS = 24


# ─────────────────────────── rule 계열 (기준선) ───────────────────────────

class FlatPrice:
    """90원 고정 입찰 — 가장 단순한 기준선.

    가격 신호를 전혀 보지 않고 전 구간 같은 값으로 응찰한다.
    낙찰은 잘 되지만 에너지 예산을 무시해 대량 위약금이 발생한다.
    """

    name = "flat90"
    family = "rule"
    description = "전 구간 90원 고정 · 정격 100kW 응찰"

    def __init__(self, price: float = 90.0, qty: float = 100.0) -> None:
        self.price, self.qty = price, qty

    def bids(self, ctx: MarketContext) -> list[Bid]:
        return [Bid(h, min(self.qty, ctx.power_kw), clamp_price(self.price, ctx.price_cap))
                for h in range(HOURS)]


class TopKPeak:
    """예측 상위 K개 구간에만 응찰 — '전략 채움'.

    직관적이지만 에너지 제약을 고려하지 않아 낙찰 후 이행하지 못한다.
    """

    name = "topk_peak"
    family = "rule"
    description = "예측가 상위 K구간 집중 · 예측가의 92% 응찰"

    def __init__(self, k: int = 8, qty: float = 100.0, ratio: float = 0.92) -> None:
        self.k, self.qty, self.ratio = k, qty, ratio

    def bids(self, ctx: MarketContext) -> list[Bid]:
        fc = ctx.fc
        top = set(np.argsort(-fc)[: self.k].tolist())
        return [
            Bid(h, min(self.qty, ctx.power_kw) if h in top else 0.0,
                clamp_price(fc[h] * self.ratio, ctx.price_cap))
            for h in range(HOURS)
        ]


class SafeTopK(TopKPeak):
    """TopK에 에너지 예산 제약만 추가한 전략.

    '제약을 아느냐 모르느냐'가 성과를 얼마나 가르는지 보여주는 대조군이다.
    """

    name = "topk_safe"
    family = "rule"
    description = "상위 K구간 응찰 + 가용 에너지 한도 강제"

    def bids(self, ctx: MarketContext) -> list[Bid]:
        return energy_feasible(super().bids(ctx), ctx)


class MarginalCostBidder(SafeTopK):
    """변동비 하한 입찰 — 발전사업자의 기본 문법을 그대로 적용.

    SafeTopK와 자원·에너지 제약은 같지만, **입찰가를 변동비 아래로 내리지 않는다.**
    충전단가÷효율 + 열화비용을 밑도는 가격에는 아예 응찰하지 않으므로,
    스프레드가 얇은 날에는 자동으로 거래를 쉰다.

    "안 파는 것도 전략이다" — 손해 보는 체결을 구조적으로 차단한다.
    """

    name = "marginal_cost"
    family = "rule"
    description = "상위 K구간 + 에너지 한도 + 변동비(충전÷효율+열화) 입찰 하한"

    def bids(self, ctx: MarketContext) -> list[Bid]:
        return energy_feasible(var_cost_floor(super(SafeTopK, self).bids(ctx), ctx), ctx)


# ─────────────────────────── optimize 계열 ───────────────────────────

class GreedyEnergyBudget:
    """탐욕 배분 — 기대 마진이 높은 구간부터 에너지를 채운다.

    마진 = 예측가 − 열화비용. 마진이 양수인 구간만, 정격과 예산 안에서 배정한다.
    퀀트로 치면 기대수익 상위 종목에 자본을 순서대로 배분하는 것과 같다.
    """

    name = "greedy_budget"
    family = "optimize"
    description = "마진 상위 구간부터 에너지 예산 소진 · 낙찰 확률 위해 예측가 대비 할인 응찰"

    def __init__(self, discount: float = 0.93) -> None:
        self.discount = discount

    def bids(self, ctx: MarketContext) -> list[Bid]:
        fc = ctx.fc
        margin = fc - ctx.degradation_won
        order = np.argsort(-margin)
        remaining = ctx.energy_kwh
        bids = [Bid(h, 0.0, clamp_price(fc[h] * self.discount, ctx.price_cap)) for h in range(HOURS)]
        for h in order:
            if margin[h] <= 0 or remaining <= 0:
                break
            take = snap(min(ctx.power_kw, remaining), ctx.min_unit_kw)
            bids[int(h)].qty_kw = take
            remaining -= take
        return bids


class MarginalValueBidder:
    """한계가치 입찰 — 에너지의 기회비용을 가격에 반영한다.

    오늘 낼 수 있는 에너지가 적을수록 "아껴 팔아야" 하므로 응찰가를 높인다.
    남는 에너지가 많으면 싸게라도 낸다. 저장자원 입찰의 교과서적 접근이다.
    기회비용은 예산으로 커버 가능한 구간 수를 기준으로 산출한다.
    """

    name = "marginal_value"
    family = "optimize"
    description = "가용 에너지의 기회비용을 응찰가에 반영 (희소할수록 비싸게)"

    def bids(self, ctx: MarketContext) -> list[Bid]:
        fc = ctx.fc
        slots = max(1, int(ctx.energy_kwh / max(ctx.power_kw, 1e-6)))
        ranked = np.sort(fc)[::-1]
        # 예산으로 채울 수 있는 마지막 구간의 예측가 = 기회비용(유보가격)
        reserve = float(ranked[min(slots, HOURS) - 1])
        bids = []
        for h in range(HOURS):
            if fc[h] < reserve:
                bids.append(Bid(h, 0.0, clamp_price(reserve, ctx.price_cap)))
                continue
            price = max(reserve, ctx.degradation_won * 1.1, fc[h] * 0.9)
            bids.append(Bid(h, ctx.power_kw, clamp_price(price, ctx.price_cap)))
        return energy_feasible(bids, ctx)


# ─────────────────────────── statistical 계열 ───────────────────────────

class ZScoreMeanReversion:
    """z-score 평균회귀 — 하루 안에서 평균 대비 비싼 구간에만 판다.

    주식 페어트레이딩의 z-score 진입 규칙을 그대로 옮긴 것이다.
    변동성이 작은 날(가격이 평평한 날)은 아예 응찰하지 않는다.
    """

    name = "zscore"
    family = "statistical"
    description = "일중 z-score > 임계값 구간만 응찰 · 변동성 낮은 날은 관망"

    def __init__(self, entry_z: float = 0.6, min_std_ratio: float = 0.03) -> None:
        self.entry_z, self.min_std_ratio = entry_z, min_std_ratio

    def bids(self, ctx: MarketContext) -> list[Bid]:
        fc = ctx.fc
        mu, sd = float(fc.mean()), float(fc.std())
        if mu <= 0 or sd / mu < self.min_std_ratio:
            return [Bid(h, 0.0, clamp_price(mu, ctx.price_cap)) for h in range(HOURS)]  # 관망
        z = (fc - mu) / sd
        bids = []
        for h in range(HOURS):
            if z[h] < self.entry_z:
                bids.append(Bid(h, 0.0, clamp_price(fc[h], ctx.price_cap)))
                continue
            # z가 클수록 확신이 크므로 사이즈를 키운다 (선형 스케일)
            size = min(1.0, (z[h] - self.entry_z) / 1.5 + 0.5)
            bids.append(Bid(h, ctx.power_kw * size, clamp_price(fc[h] * 0.9, ctx.price_cap)))
        return energy_feasible(bids, ctx)


class VolatilityScaled:
    """변동성 타겟팅 — 예측 스프레드가 클수록 크게, 작을수록 작게 응찰.

    퀀트의 변동성 타겟 포지션 사이징과 같은 발상이다. 기회가 큰 날에 집중하고
    평평한 날에는 열화비용만 쓰는 무의미한 거래를 피한다.
    """

    name = "vol_scaled"
    family = "statistical"
    description = "일중 가격 스프레드에 비례해 노출 조절 · 상위 분위 구간 집중"

    def __init__(self, target_spread: float = 25.0, quantile: float = 0.7) -> None:
        self.target_spread, self.quantile = target_spread, quantile

    def bids(self, ctx: MarketContext) -> list[Bid]:
        fc = ctx.fc
        spread = float(np.percentile(fc, 90) - np.percentile(fc, 10))
        exposure = float(np.clip(spread / self.target_spread, 0.2, 1.0))
        thresh = float(np.quantile(fc, self.quantile))
        bids = []
        for h in range(HOURS):
            if fc[h] < thresh:
                bids.append(Bid(h, 0.0, clamp_price(fc[h], ctx.price_cap)))
                continue
            bids.append(Bid(h, ctx.power_kw * exposure, clamp_price(fc[h] * 0.91, ctx.price_cap)))
        return energy_feasible(bids, ctx)


class PenaltyAwareCVaR:
    """위약금 회피형 — 예측 오차의 하위 꼬리(CVaR)를 가정해 보수적으로 응찰.

    예측이 틀려 낙찰이 몰릴 경우를 대비해 예산의 일정 비율만 노출한다.
    금융 리스크 관리의 CVaR(조건부 기대손실) 개념을 적용했다.
    """

    name = "cvar_guard"
    family = "statistical"
    description = "예측 오차 꼬리 리스크를 반영해 예산의 일부만 노출 (보수적)"

    def __init__(self, exposure: float = 0.75, error_pct: float = 0.05) -> None:
        self.exposure, self.error_pct = exposure, error_pct

    def bids(self, ctx: MarketContext) -> list[Bid]:
        fc = ctx.fc
        # 예측이 낙관적이었을 경우를 가정한 하방 시나리오
        pessimistic = fc * (1 - self.error_pct)
        margin = pessimistic - ctx.degradation_won
        budget = ctx.energy_kwh * self.exposure
        order = np.argsort(-margin)
        bids = [Bid(h, 0.0, clamp_price(pessimistic[h] * 0.95, ctx.price_cap)) for h in range(HOURS)]
        remaining = budget
        for h in order:
            if margin[h] <= 0 or remaining <= 0:
                break
            take = snap(min(ctx.power_kw, remaining), ctx.min_unit_kw)
            bids[int(h)].qty_kw = take
            remaining -= take
        return bids


# ─────────────────────────── learned 계열 ───────────────────────────

class CEMPolicy:
    """CEM(교차엔트로피법)으로 학습한 신경망 정책 — 기존 models/bid_policy.json.

    5입력 → 은닉 8 → (수량비율, 가격비율) 2출력의 작은 MLP.
    numpy만으로 추론한다 (배포 경량화 원칙).
    """

    name = "cem_policy"
    family = "learned"
    description = "CEM 학습 정책 (5-8-2 MLP) · 10년 실데이터 시장에서 학습"

    def __init__(self, weights_path: str | None = None) -> None:
        self._m: dict | None = None
        self._path = weights_path

    def _load(self) -> dict | None:
        if self._m is None:
            import json
            from pathlib import Path

            p = (Path(self._path) if self._path
                 else Path(__file__).resolve().parents[3] / "models" / "bid_policy.json")
            try:
                self._m = json.load(open(p))
            except Exception:
                self._m = {}
        return self._m or None

    def bids(self, ctx: MarketContext) -> list[Bid]:
        m = self._load()
        if not m:
            # 가중치가 없으면 안전한 기준선으로 대체 (서비스 중단 방지)
            return GreedyEnergyBudget().bids(ctx)
        n_in, n_h, _ = m["arch"]
        th = np.asarray(m["weights"], dtype=float)
        W1 = th[: n_in * n_h].reshape(n_in, n_h)
        b1 = th[n_in * n_h: n_in * n_h + n_h]
        o = n_in * n_h + n_h
        W2 = th[o: o + n_h * 2].reshape(n_h, 2)
        b2 = th[o + n_h * 2:]

        fc = ctx.fc
        mx = float(fc.max()) or 1.0
        rank = np.argsort(np.argsort(fc)) / (HOURS - 1)
        bids = []
        for h in range(HOURS):
            x = np.array([
                fc[h] / mx,
                math.sin(2 * math.pi * h / HOURS),
                math.cos(2 * math.pi * h / HOURS),
                rank[h],
                ctx.energy_kwh / max(ctx.power_kw * HOURS, 1e-6),
            ])
            hdn = np.tanh(x @ W1 + b1)
            q, p = 1 / (1 + np.exp(-(hdn @ W2 + b2)))
            qty = snap(float(q) * ctx.power_kw, ctx.min_unit_kw) if q > 0.35 else 0.0
            bids.append(Bid(h, qty, clamp_price(fc[h] * (0.75 + 0.24 * float(p)), ctx.price_cap)))
        return bids


# ─────────────────────────── meta 계열 ───────────────────────────

class EnsembleMedian:
    """앙상블 — 여러 전략의 중앙값을 취한다.

    한 전략이 특정 국면에서 무너져도 중앙값이 이를 흡수한다.
    퀀트의 모델 앙상블과 같은 목적(분산 축소)이다.
    """

    name = "ensemble"
    family = "meta"
    description = "구성 전략들의 수량·가격 중앙값 · 단일 전략 붕괴 위험 완화"

    def __init__(self, members: list | None = None) -> None:
        self.members = members or [GreedyEnergyBudget(), MarginalValueBidder(),
                                   VolatilityScaled(), CEMPolicy()]

    def bids(self, ctx: MarketContext) -> list[Bid]:
        mats_q, mats_p = [], []
        for m in self.members:
            bs = m.bids(ctx)
            mats_q.append([b.qty_kw for b in bs])
            mats_p.append([b.price for b in bs])
        q = np.median(np.asarray(mats_q), axis=0)
        p = np.median(np.asarray(mats_p), axis=0)
        bids = [Bid(h, snap(float(q[h]), ctx.min_unit_kw), clamp_price(float(p[h]), ctx.price_cap))
                for h in range(HOURS)]
        return energy_feasible(bids, ctx)


class BanditSelector:
    """온라인 학습형 메타 전략 — 지수가중 밴딧(EXP3 계열).

    매일 실현 손익을 받아 전략별 가중치를 갱신하고, 다음 날 가장 유망한 전략을 고른다.
    시장 국면이 바뀌면 자동으로 갈아탄다. 정보는 '어제까지'만 사용한다.
    """

    name = "bandit"
    family = "meta"
    description = "일별 실현손익으로 전략 가중치 갱신 · 국면 변화 시 자동 전환"

    def __init__(self, members: list | None = None, lr: float = 0.35, explore: float = 0.08) -> None:
        self.members = members or [GreedyEnergyBudget(), MarginalValueBidder(),
                                   ZScoreMeanReversion(), VolatilityScaled(),
                                   PenaltyAwareCVaR(), CEMPolicy()]
        self.lr, self.explore = lr, explore
        self.w = np.ones(len(self.members))
        self.last_idx: int | None = None

    def reset(self) -> None:
        self.w = np.ones(len(self.members))
        self.last_idx = None

    def _probs(self) -> np.ndarray:
        w = self.w / self.w.sum()
        return (1 - self.explore) * w + self.explore / len(self.members)

    def bids(self, ctx: MarketContext) -> list[Bid]:
        p = self._probs()
        idx = int(np.argmax(p))  # 운영에서는 결정적으로 최선을 고른다
        self.last_idx = idx
        return self.members[idx].bids(ctx)

    def update(self, realized_pnl: float, scale: float = 50_000.0) -> None:
        """하루가 끝난 뒤 실현 손익으로 가중치 갱신 (지수 가중)."""
        if self.last_idx is None:
            return
        r = float(np.clip(realized_pnl / scale, -1.0, 1.0))
        self.w[self.last_idx] *= math.exp(self.lr * r)
        self.w = np.clip(self.w, 1e-3, 1e3)


from .stochastic import StochasticCVaR  # noqa: E402


def registry() -> dict:
    """벤치마크 대상 전략 목록 — 이름 → 인스턴스 팩토리."""
    return {
        "flat90": FlatPrice,
        "topk_peak": TopKPeak,
        "topk_safe": SafeTopK,
        "marginal_cost": MarginalCostBidder,
        "greedy_budget": GreedyEnergyBudget,
        "marginal_value": MarginalValueBidder,
        "zscore": ZScoreMeanReversion,
        "vol_scaled": VolatilityScaled,
        "cvar_guard": PenaltyAwareCVaR,
        "cem_policy": CEMPolicy,
        "stochastic_cvar": StochasticCVaR,
        "ensemble": EnsembleMedian,
        "bandit": BanditSelector,
    }

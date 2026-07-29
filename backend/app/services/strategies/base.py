"""전략 프레임워크 공통 정의 — 퀀트 백테스트 구조를 VPP 입찰에 이식.

주식 퀀트와의 대응 관계:
    종목 유니버스   → 24개 시간 구간(슬롯)
    매수/매도 사이즈 → 입찰 수량(kW)
    지정가 주문     → 입찰가(₩/kWh) — MCP 이하일 때만 체결(낙찰)
    슬리피지·수수료 → 배터리 열화비용 + 미이행 위약금
    포지션 한도     → 방전 정격(kW)·가용 에너지(kWh)

핵심 차이는 **에너지 예산 제약**이다. 주식은 같은 종목을 계속 살 수 있지만,
배터리는 하루에 낼 수 있는 총 에너지가 정해져 있어 "어느 시간에 쓸지"가 곧 전략이다.
많이 응찰해 낙찰돼도 낼 에너지가 없으면 위약금을 문다 — 이것이 손실의 주된 원인이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

HOURS = 24


@dataclass
class MarketContext:
    """전략이 입찰을 짤 때 참조하는 정보 (미래 실현가는 절대 포함하지 않는다)."""

    forecast: list[float]        # 예측 MCP 24개 (₩/kWh)
    power_kw: float              # 총 방전 정격 (kW)
    energy_kwh: float            # 오늘 낼 수 있는 총 에너지 (kWh)
    price_cap: float             # 입찰 상한가
    min_unit_kw: float           # 최소 입찰 단위
    degradation_won: float       # 열화비용 (₩/kWh)
    # ── 변동비 항목 ──────────────────────────────────────────
    # 우리는 연료를 태우지 않지만 **충전 전기를 사와야 한다**. 그것이 우리의 연료비다.
    # 여기에 왕복효율 손실이 붙는다: 90kWh를 팔려면 100kWh를 사야 한다.
    charge_cost_won: float = 0.0     # 충전 전기 구입 단가 (₩/kWh, 효율 반영 전)
    round_trip_eff: float = 0.90     # 왕복효율 (충전→방전 손실)
    # 과거 실현 데이터 — 온라인 학습형 전략만 사용 (룩어헤드 방지: 어제까지의 정보)
    history: list[dict] = field(default_factory=list)

    @property
    def fc(self) -> np.ndarray:
        return np.asarray(self.forecast, dtype=float)

    @property
    def var_cost_won(self) -> float:
        """방전 1kWh의 변동비 = 충전단가 ÷ 왕복효율 + 열화비용.

        발전소의 변동비(연료비)와 정확히 같은 위치에 있는 값이다.
        **MCP가 이 값보다 낮으면 파는 순간 손해**이므로 입찰 하한이 된다.
        """
        eff = max(0.05, self.round_trip_eff)
        return self.charge_cost_won / eff + self.degradation_won


@dataclass
class Bid:
    hour: int
    qty_kw: float
    price: float


class Strategy(Protocol):
    """모든 전략이 지켜야 하는 인터페이스."""

    name: str
    family: str      # rule / optimize / statistical / learned / meta
    description: str

    def bids(self, ctx: MarketContext) -> list[Bid]:
        ...


def snap(qty: float, unit: float) -> float:
    """최소 입찰 단위로 내림 스냅 (시장 문법)."""
    if qty < unit:
        return 0.0
    return float(int(qty / unit) * unit)


def clamp_price(price: float, cap: float) -> float:
    return float(round(min(max(price, 0.0), cap), 1))


def var_cost_floor(bids: list[Bid], ctx: MarketContext) -> list[Bid]:
    """변동비 이하로는 응찰하지 않는다 — 발전사업자의 기본 문법.

    pay-as-clear에서 입찰가는 '이 가격 이상이면 팔겠다'는 하한선이다.
    입찰가를 변동비로 올려두면, MCP가 변동비를 밑도는 날에는 자동으로 미낙찰되어
    **손해 보는 체결 자체가 생기지 않는다.** (기회비용을 잃는 대신 하방을 막는다)

    이 장치가 없으면 전략은 '싸도 일단 팔고 보는' 행동을 하고,
    스프레드가 열화비용보다 작은 날에 구조적으로 적자를 낸다.
    """
    floor = ctx.var_cost_won
    if floor <= 0:
        return bids
    return [Bid(b.hour, b.qty_kw, clamp_price(max(b.price, floor), ctx.price_cap)) for b in bids]


def energy_feasible(bids: list[Bid], ctx: MarketContext) -> list[Bid]:
    """에너지 예산 안으로 강제 축소 — 전 전략 공통 안전장치.

    낙찰 가능성이 높은(=입찰가가 낮은) 구간부터 예산을 배정하고,
    예산을 넘는 구간은 잘라낸다. 위약금의 구조적 원인을 차단한다.
    """
    order = sorted(range(len(bids)), key=lambda i: (bids[i].price, -bids[i].qty_kw))
    remaining = ctx.energy_kwh
    out = [Bid(b.hour, 0.0, b.price) for b in bids]
    for i in order:
        b = bids[i]
        if b.qty_kw <= 0:
            continue
        take = min(b.qty_kw, remaining, ctx.power_kw)  # 1시간 기준 kW ≈ kWh
        take = snap(take, ctx.min_unit_kw)
        out[i].qty_kw = take
        remaining -= take
        if remaining <= 0:
            break
    return out

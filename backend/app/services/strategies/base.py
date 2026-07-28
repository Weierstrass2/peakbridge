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
    # 과거 실현 데이터 — 온라인 학습형 전략만 사용 (룩어헤드 방지: 어제까지의 정보)
    history: list[dict] = field(default_factory=list)

    @property
    def fc(self) -> np.ndarray:
        return np.asarray(self.forecast, dtype=float)


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

"""피크 예약 — 시장에 팔기 전에 아파트 본업부터 지킨다.

── 왜 필요한가 ────────────────────────────────────────────────

기존 입찰 로직은 **가격과 SOC만** 보고 있었다. 아파트가 그 시간에 전기를
얼마나 쓸지는 전혀 보지 않았다. 그래서 이런 일이 가능했다.

    14시  시장가 130원 → 배터리를 다 팔아버림 (SOC 20%)
    15시  아파트 피크 발생 → 배터리 텅 빔 → 한전에서 그대로 끌어씀
          → 그달 기본요금 확정

시장에서 몇십만 원 벌고, 기본요금으로 그 이상을 잃는다.
게다가 기본요금은 **그 순간 한 번**으로 정해지므로 되돌릴 수 없다.

── 이건 기회비용 문제다 ────────────────────────────────────────

배터리 1kWh를 두고 두 용도가 경쟁한다.

    시장에 판다      → kWh당 시장가 (예: 130원)
    피크쉐이빙에 쓴다 → 그 시간 피크를 깎아 아끼는 기본요금

문제는 **단위가 다르다는 것**이다.
시장 판매는 kWh(에너지)로 벌고, 피크쉐이빙은 kW(순간 출력)로 번다.
그리고 기본요금은 한 달에 딱 한 번의 최고점으로 결정된다.

그래서 이렇게 뒤집힌다.

    오늘이 그달 최고점이 될 것 같은 날 → 피크 가치가 시장가를 압도. 팔면 안 된다
    이미 이번 달 최고점이 지나간 날     → 더 써도 기본요금이 안 오른다. 팔아도 된다

즉 **"오늘이 그달 최고점을 갱신할 확률"**이 판단의 핵심 변수다.

── 이 모듈이 하는 일 ──────────────────────────────────────────

  1. 수요예측으로 시간대별 예상 부하를 받는다
  2. 계약전력(또는 이번 달 최대수요) 대비 초과분을 구한다
  3. 그 초과분을 깎는 데 필요한 에너지를 **예약**한다 (시장에 못 팔게 잠금)
  4. 예약 구간은 입찰에서 제외한다 (blackout)
  5. 남은 에너지만 시장 입찰로 넘긴다

주의: 기본요금 산정 방식(당월 최대 vs 직전 12개월 최대)은 요금제마다 다르다.
      12개월 방식이면 한 번 놓친 피크가 1년을 따라다니므로 피크 가치가 몇 배 커진다.
      lookback_months 로 그 차이를 반영한다. 실증 단지 고지서로 확정해야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import Bid, MarketContext

HOURS = 24

# 기본요금 단가 (₩/kW·월). 계약종별로 다르므로 근사값이며 고지서로 교체해야 한다.
DEFAULT_BASE_RATE_WON_PER_KW = 8_320.0


@dataclass
class PeakPlan:
    """오늘의 피크 예약 계획."""

    reserved_kwh: float                       # 시장에 못 파는 에너지
    blackout_hours: set[int]                  # 입찰 금지 시간
    peak_hours: list[int]                     # 피크 위험 시간 (참고)
    expected_peak_kw: float                   # 오늘 예상 최대수요
    month_peak_kw: float                      # 이번 달 현재까지 최대수요
    headroom_kw: float                        # 계약전력까지 남은 여유
    shave_kw: float                           # 깎아야 하는 양
    peak_value_won_per_kwh: float             # 피크쉐이빙 1kWh의 가치
    renews_month_peak: bool                   # 오늘이 그달 최고점을 갱신하는가
    detail: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "reserved_kwh": round(self.reserved_kwh, 1),
            "blackout_hours": sorted(self.blackout_hours),
            "peak_hours": self.peak_hours,
            "expected_peak_kw": round(self.expected_peak_kw, 1),
            "month_peak_kw": round(self.month_peak_kw, 1),
            "headroom_kw": round(self.headroom_kw, 1),
            "shave_kw": round(self.shave_kw, 1),
            "peak_value_won_per_kwh": round(self.peak_value_won_per_kwh, 1),
            "renews_month_peak": self.renews_month_peak,
            "detail": self.detail,
        }


def peak_value(shave_kw: float, shave_kwh: float, base_rate: float,
               lookback_months: int = 1) -> float:
    """피크쉐이빙 1kWh의 가치 (₩/kWh).

    깎은 kW × 기본요금 단가 × 적용 개월수 를, 그걸 위해 쓴 kWh로 나눈다.

        가치 = (shave_kw × base_rate × months) / shave_kwh

    직관: 3시간 동안 30kW를 깎으려면 90kWh가 필요하지만,
    그 대가로 30kW × 8,320원 = 249,600원의 기본요금이 매달 줄어든다.
    → kWh당 2,773원. 시장가(130원)와 비교가 안 된다.

    **이 비대칭이 "팔지 마라"의 근거다.**
    """
    if shave_kwh <= 1e-9 or shave_kw <= 0:
        return 0.0
    return shave_kw * base_rate * max(1, lookback_months) / shave_kwh


def plan_reservation(
    demand_kw: list[float],
    contract_kw: float,
    power_kw: float,
    energy_kwh: float,
    month_peak_kw: float = 0.0,
    base_rate: float = DEFAULT_BASE_RATE_WON_PER_KW,
    lookback_months: int = 1,
    safety: float = 1.15,
) -> PeakPlan:
    """수요예측 → 피크 예약 계획.

    demand_kw       시간대별 예상 부하 (24개, kW)
    contract_kw     계약전력 — 이걸 넘기면 기본요금이 오른다
    power_kw        배터리 방전 정격
    energy_kwh      현재 가용 에너지
    month_peak_kw   이번 달 현재까지 최대수요 (0이면 미상 → 보수적으로 예약)
    lookback_months 기본요금 산정 기간 (1=당월, 12=직전 12개월 최대)
    safety          예측 오차 대비 안전계수
    """
    dm = list(demand_kw)[:HOURS] + [0.0] * max(0, HOURS - len(demand_kw))
    expected_peak = max(dm) if dm else 0.0

    # 기준선 = 계약전력과 '이번 달 이미 찍힌 최대수요' 중 **높은 쪽**.
    #
    # 기본요금은 그달 최대수요 하나로 정해진다. 이미 230kW가 찍혔다면
    # 오늘 225kW를 깎아봐야 청구액은 그대로다 — 이미 진 싸움이다.
    # 그 경우 배터리를 잠가둘 이유가 없으므로 시장에 파는 게 옳다.
    guard = max(contract_kw, max(month_peak_kw, 0.0))
    renews = expected_peak > guard

    detail: list[dict] = []
    blackout: set[int] = set()
    reserved = 0.0
    total_shave_kw = 0.0

    for h, d in enumerate(dm):
        over = d * safety - guard          # 안전계수를 얹어 초과분 계산
        if over <= 0:
            continue
        shave = min(over, power_kw)        # 정격 이상은 못 깎는다
        need = shave                       # 1시간 급전 → kW ≈ kWh
        reserved += need
        total_shave_kw = max(total_shave_kw, shave)
        blackout.add(h)
        detail.append({
            "hour": h,
            "demand_kw": round(d, 1),
            "over_kw": round(over, 1),
            "shave_kw": round(shave, 1),
            "reserve_kwh": round(need, 1),
        })

    # 가용 에너지를 넘어서 예약할 수는 없다
    reserved = min(reserved, energy_kwh)
    pv = peak_value(total_shave_kw, max(reserved, 1e-9), base_rate, lookback_months)

    # 오늘이 그달 최고점을 갱신하지 않는다면 피크 가치는 0에 가깝다 → 예약 해제
    if not renews:
        reserved, blackout, pv = 0.0, set(), 0.0

    return PeakPlan(
        reserved_kwh=reserved,
        blackout_hours=blackout,
        peak_hours=[d["hour"] for d in detail],
        expected_peak_kw=expected_peak,
        month_peak_kw=month_peak_kw,
        headroom_kw=guard - expected_peak,
        shave_kw=total_shave_kw,
        peak_value_won_per_kwh=pv,
        renews_month_peak=renews,
        detail=detail,
    )


def apply_reservation(bids: list[Bid], ctx: MarketContext, plan: PeakPlan) -> list[Bid]:
    """입찰서에서 예약 구간을 걷어낸다.

    두 단계로 막는다.
      1. blackout: 피크 위험 시간은 아예 응찰하지 않는다 (수량 0)
      2. 나머지 구간도 남은 에너지(=총량 − 예약분) 안으로 축소한다

    2번이 없으면 피크 시간을 피해 다른 시간에 다 팔아버려서
    정작 피크 때 배터리가 비는 결과가 나온다. 시간이 아니라 **에너지**를 지켜야 한다.
    """
    if plan.reserved_kwh <= 0 and not plan.blackout_hours:
        return bids

    remaining = max(0.0, ctx.energy_kwh - plan.reserved_kwh)
    out = [Bid(b.hour, 0.0, b.price) for b in bids]

    # 낙찰 가능성이 높은(가격이 낮은) 구간부터 남은 예산을 배정
    order = sorted(range(len(bids)), key=lambda i: (bids[i].price, -bids[i].qty_kw))
    for i in order:
        b = bids[i]
        if b.qty_kw <= 0 or b.hour in plan.blackout_hours:
            continue
        take = min(b.qty_kw, remaining, ctx.power_kw)
        if take < ctx.min_unit_kw:
            continue
        take = float(int(take / ctx.min_unit_kw) * ctx.min_unit_kw)
        out[i].qty_kw = take
        remaining -= take
        if remaining <= 0:
            break
    return out


def compare_uses(plan: PeakPlan, forecast: list[float]) -> dict:
    """같은 1kWh를 시장에 팔 때 vs 피크에 쓸 때 — 심사용 대조표."""
    peak_prices = [forecast[h] for h in plan.peak_hours if h < len(forecast)]
    market = max(peak_prices) if peak_prices else (max(forecast) if forecast else 0.0)
    pv = plan.peak_value_won_per_kwh
    return {
        "market_won_per_kwh": round(market, 1),
        "peak_won_per_kwh": round(pv, 1),
        "ratio": round(pv / market, 1) if market > 0 else None,
        "verdict": (
            f"피크쉐이빙이 시장 판매보다 {pv / market:.0f}배 가치가 크다 — 예약 유지"
            if market > 0 and pv > market else
            "이번 달 최고점이 이미 지났다 — 시장 판매 허용"
            if not plan.renews_month_peak else
            "시장 판매가 유리 — 예약 최소화"
        ),
    }

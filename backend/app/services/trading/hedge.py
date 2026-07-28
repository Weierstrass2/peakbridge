"""실시간시장 헤지 — 하루전 포지션의 이행 부족분을 RT에서 되사 위약금을 피한다.

전력 트레이딩의 핵심 방어 논리다.

    하루전시장에서 100kW를 팔았다 (인도 의무 발생)
    → 급전 시점에 배터리가 70kW밖에 못 낸다
    → 부족분 30kW를 그냥 두면: 위약금 = 30 × MCP × 1.2
    → 실시간시장에서 30kW를 사서 메우면: 비용 = 30 × RT가격

    RT가격 < MCP × 1.2 이면 헤지가 유리하다.

이것이 제주 실시간시장 시범사업이 열어준 구조이며, 금융시장에서
선물 포지션을 현물로 커버하는 것과 같은 발상이다.

주의: 헤지도 공짜가 아니다. RT 가격이 급등하면 위약금보다 비쌀 수 있다.
      그래서 '무조건 헤지'가 아니라 **비용 비교 후 결정**한다.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)

# RT 시장에서 우리가 사들일 때 붙는 비용 (호가 스프레드·슬리피지)
RT_BUY_SPREAD = 0.03


@dataclass
class HedgeDecision:
    hour: int
    obligation_kw: float      # 하루전 낙찰로 생긴 인도 의무
    deliverable_kw: float     # 실제로 낼 수 있는 양
    shortfall_kw: float       # 부족분
    rt_price: float           # 실시간시장 매수가
    penalty_price: float      # 위약 단가 (MCP × 위약계수)
    action: str               # "hedge" | "accept_penalty" | "none"
    cost_won: float           # 선택한 방법의 비용
    saved_won: float          # 회피한 금액 (위약금 − 헤지비용)
    reason: str

    def to_dict(self) -> dict:
        return {
            "hour": self.hour,
            "obligation_kw": round(self.obligation_kw, 1),
            "deliverable_kw": round(self.deliverable_kw, 1),
            "shortfall_kw": round(self.shortfall_kw, 1),
            "rt_price": round(self.rt_price, 1),
            "penalty_price": round(self.penalty_price, 1),
            "action": self.action,
            "cost_won": round(self.cost_won),
            "saved_won": round(self.saved_won),
            "reason": self.reason,
        }


def plan_hedge(awarded: list[dict], available_kwh: float, mcp: list[float],
               rt_prices: list[float] | None = None,
               penalty_factor: float = 1.2) -> dict:
    """이행 계획을 세우고 부족 구간마다 헤지 여부를 판단한다.

    awarded: [{"hour": h, "qty_kw": q}] — 하루전 낙찰 물량
    available_kwh: 급전 시점 실제 가용 에너지
    mcp: 시간대별 확정 가격 (위약 산정 기준)
    rt_prices: 실시간시장 가격. 없으면 MCP 기준으로 추정한다.
    """
    rt = rt_prices or [p * (1 + RT_BUY_SPREAD) for p in mcp]
    left = available_kwh
    decisions: list[HedgeDecision] = []

    # 인도 의무는 시간 순서대로 발생한다 (앞 구간이 에너지를 먼저 쓴다)
    for row in sorted(awarded, key=lambda r: int(r["hour"])):
        h = int(row["hour"])
        q = float(row.get("qty_kw", 0) or 0)
        if q <= 0:
            continue
        deliver = min(q, left)
        left -= deliver
        short = q - deliver
        if short <= 0.5:
            decisions.append(HedgeDecision(h, q, deliver, 0.0, rt[h], mcp[h] * penalty_factor,
                                           "none", 0.0, 0.0, "부족 없음 — 자체 이행"))
            continue

        penalty_price = mcp[h] * penalty_factor
        penalty_cost = short * penalty_price
        hedge_cost = short * rt[h]

        if hedge_cost < penalty_cost:
            decisions.append(HedgeDecision(
                h, q, deliver, short, rt[h], penalty_price, "hedge",
                hedge_cost, penalty_cost - hedge_cost,
                f"RT ₩{rt[h]:,.1f} < 위약 ₩{penalty_price:,.1f} — 매수 커버가 유리",
            ))
        else:
            decisions.append(HedgeDecision(
                h, q, deliver, short, rt[h], penalty_price, "accept_penalty",
                penalty_cost, 0.0,
                f"RT ₩{rt[h]:,.1f} ≥ 위약 ₩{penalty_price:,.1f} — 헤지가 더 비쌈",
            ))

    hedged = [d for d in decisions if d.action == "hedge"]
    accepted = [d for d in decisions if d.action == "accept_penalty"]
    return {
        "decisions": [d.to_dict() for d in decisions],
        "summary": {
            "obligation_kwh": round(sum(d.obligation_kw for d in decisions), 1),
            "deliverable_kwh": round(sum(d.deliverable_kw for d in decisions), 1),
            "shortfall_kwh": round(sum(d.shortfall_kw for d in decisions), 1),
            "hedged_kwh": round(sum(d.shortfall_kw for d in hedged), 1),
            "hedge_cost_won": round(sum(d.cost_won for d in hedged)),
            "penalty_avoided_won": round(sum(d.saved_won for d in hedged)),
            "penalty_paid_won": round(sum(d.cost_won for d in accepted)),
            "hedge_count": len(hedged),
            "coverage_after": round(
                (sum(d.deliverable_kw for d in decisions) + sum(d.shortfall_kw for d in hedged))
                / max(sum(d.obligation_kw for d in decisions), 1e-9), 3
            ),
        },
    }


def hedged_pnl(base_pnl: float, plan: dict) -> dict:
    """헤지를 적용했을 때와 안 했을 때의 손익 비교.

    base_pnl은 '헤지 없이 위약금을 전부 문' 경우의 순손익이다.
    """
    s = plan["summary"]
    avoided = s["penalty_avoided_won"]
    return {
        "without_hedge_won": round(base_pnl),
        "with_hedge_won": round(base_pnl + avoided),
        "improvement_won": round(avoided),
        "hedge_cost_won": s["hedge_cost_won"],
        "coverage_after": s["coverage_after"],
    }

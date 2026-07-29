"""제주 플러스 DR 참여 엔진 — 실측 데이터 기반.

── 이전 모델이 왜 폐기됐는가 ──────────────────────────────────

이전 제주 엔진(jeju.py)은 이렇게 전제했다.

    출력제어가 걸리면 전기가 남는다 → 가격이 0원에 수렴 → 공짜 연료

**전력거래소 실측이 이 전제를 반박했다.**

    출력제어 시각의 제주 SMP : 평균 173.2원 (최저 65.6원)
    60원 이하인 경우          : 0.0%

한국 시장에서 SMP는 **한계 발전기(LNG·중유)의 변동비**로 정해진다.
재생에너지가 물리적으로 잘려나가도 가격은 화력 기준으로 유지된다.
즉 **남는 전력을 싸게 사는 메커니즘이 현행 제도에 없다.**

── 그래서 정부는 가격 대신 인센티브를 쓴다 ────────────────────

가격이 안 떨어지니 수요가 스스로 늘지 않는다. 그래서 전력거래소는
**따로 돈을 주고 수요를 끌어올린다** — 그것이 플러스 DR(수요증대 DR)이다.

일반 DR : 전기를 덜 쓰면 보상   (공급 부족 대응)
플러스DR: 전기를 더 쓰면 보상   (공급 과잉 대응)  ← 제주

── 실적이 드러낸 시장의 빈틈 (2021~2023, 90일 272건) ──────────

    입찰 1,444.5 MWh → 낙찰 1,444.5 MWh   **낙찰률 100%**
    낙찰 1,444.5 MWh → 증대   602.0 MWh   **이행률 41.7%**

    이행률 중앙값 21.2% · 100% 달성 6%

두 숫자가 사업의 전부다.

  낙찰률 100% — 입찰하면 전부 낙찰된다. **경쟁이 없다.**
                거래소는 참여자를 더 원하는데 나서는 곳이 없다.

  이행률 41.7% — 낙찰받고도 절반 이상 못 지킨다. 당연하다.
                기존 참여자는 공장·건물이고, "지금부터 더 쓰라"는 지시를 받아도
                **쓸 데가 없으면 못 쓴다.**

**배터리는 시키면 100% 한다.** 충전 버튼을 누르면 끝이기 때문이다.
우리가 파는 것은 전기가 아니라 **이행 확실성**이다.

── 정직성 고지 ────────────────────────────────────────────────

플러스 DR **정산 단가**는 공개 데이터에 없다. 그래서 이 모듈은 단가를 가정하지 않고
`breakeven_incentive()`로 **"인센티브가 얼마 이상이어야 성립하는가"**를 계산해 보고한다.
화면에도 가정값과 손익분기를 함께 표시한다.
"""

from __future__ import annotations

import json
import math
import random
import statistics
from dataclasses import dataclass, field
from pathlib import Path

FACTS_PATH = Path(__file__).resolve().parents[3] / "data" / "jeju_facts.json"

# 실측 기본값 (jeju_facts.json 이 없을 때의 폴백 — 위 분석에서 나온 값)
FALLBACK = {
    "clearing_rate": 1.0,
    "delivery_rate": 0.417,
    "delivery_pct_median": 21.2,
    "full_delivery_share": 0.06,
    "smp_mean": 173.2,
    "smp_min": 65.6,
    "event_days_per_year": 30,       # 플러스DR 실시일 (90일 / 3년)
    "curtail_days_per_year": 86.0,
    "event_hours": [11, 12, 13, 14, 15],
    "avg_cleared_per_event_mwh": 5.3,
}


def load_facts() -> dict:
    """적재된 실측 통계. 없으면 폴백."""
    try:
        d = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
        pdr, cur = d.get("plus_dr", {}), d.get("curtailment", {})
        years = max(1, len(pdr.get("years", []) or [1]))
        hours = [int(h) for h in (pdr.get("hour_hist") or {})] or FALLBACK["event_hours"]
        return {
            "clearing_rate": pdr.get("clearing_rate") or FALLBACK["clearing_rate"],
            "delivery_rate": pdr.get("delivery_rate") or FALLBACK["delivery_rate"],
            "delivery_pct_median": pdr.get("delivery_pct_median") or FALLBACK["delivery_pct_median"],
            "full_delivery_share": pdr.get("full_delivery_share") or FALLBACK["full_delivery_share"],
            "smp_mean": pdr.get("smp_mean") or FALLBACK["smp_mean"],
            "smp_min": pdr.get("smp_min") or FALLBACK["smp_min"],
            "event_days_per_year": round((pdr.get("event_days") or 90) / years, 1),
            "curtail_days_per_year": cur.get("days_per_year") or FALLBACK["curtail_days_per_year"],
            "event_hours": sorted(hours),
            "avg_cleared_per_event_mwh": round(
                (pdr.get("cleared_mwh") or 0) / max(pdr.get("records") or 1, 1), 2
            ) or FALLBACK["avg_cleared_per_event_mwh"],
            "_loaded": True,
            "_records": pdr.get("records"),
            "_years": pdr.get("years"),
        }
    except Exception:  # noqa: BLE001
        return {**FALLBACK, "_loaded": False}


# ══════════════════════════════════════════════════════════════
#  자원 · 정산
# ══════════════════════════════════════════════════════════════

@dataclass
class Fleet:
    """플러스 DR에 투입하는 배터리 포트폴리오.

    단지 한 곳으로는 시장에 못 들어간다. 여러 단지를 묶어야 의미가 생긴다.
    """

    sites: int = 100                     # 참여 단지 수
    power_kw_per_site: float = 225.0     # 단지당 충전 정격
    energy_kwh_per_site: float = 180.0   # 단지당 용량
    headroom: float = 0.55               # 이벤트 시점에 비어 있는 비율 (충전 여력)
    reliability: float = 0.97            # 우리 이행 신뢰도 (통신·고장 감안)
    eff_charge: float = 0.95
    degradation_won: float = 50.0        # 방전 kWh당 열화비용

    @property
    def power_mw(self) -> float:
        return self.sites * self.power_kw_per_site / 1000.0

    @property
    def usable_mwh(self) -> float:
        """이벤트 1회에 흡수 가능한 에너지 (MWh)."""
        return self.sites * self.energy_kwh_per_site * self.headroom / 1000.0


# 계시별 요금 (₩/kWh) — 실증 단지 고지서로 교체해야 하는 근사값
TOU_OFF, TOU_MID, TOU_PEAK = 70.0, 110.0, 180.0
BASE_RATE_WON_PER_KW = 8_320.0     # 기본요금 단가 (₩/kW·월)


def tou_at(hour: int) -> float:
    """시각별 소매 요금."""
    if hour < 9 or hour >= 23:
        return TOU_OFF
    if 10 <= hour < 12 or 13 <= hour < 19:
        return TOU_PEAK
    return TOU_MID


def is_peak_hour(hour: int) -> bool:
    return 10 <= hour < 12 or 13 <= hour < 19


@dataclass
class Settlement:
    """이벤트 1회 정산.

    ── 여기에 이 사업의 핵심 긴장이 있다 ──────────────────────

    플러스 DR은 **11~16시에 전기를 더 쓰라**고 요구한다 (실측 이벤트 시간대).
    그런데 그 시간은 아파트 **최대부하 시간대**이기도 하다.

    즉 DR에 참여하면:
        + 인센티브를 받는다
        − 비싼 시간대 요금으로 전기를 산다 (경부하가 아니다)
        − **계량기 피크가 올라가 기본요금이 오를 수 있다**  ← 가장 큰 위험

    기본요금은 그달 최고 순간 하나로 정해지므로, DR 한 번 참여했다가
    그달 내내 더 내는 일이 생긴다. 기존 참여자들이 이행하지 못하는 이유도
    상당 부분 이 충돌 때문이다.

    **그래서 이 시장의 진짜 문제는 '더 쓸 수 있느냐'가 아니라
    '피크를 올리지 않고 더 쓸 수 있느냐'다.**
    우리는 피크 예약 엔진으로 그걸 계산할 수 있다 — 이게 차별점이다.
    """

    cleared_mwh: float
    delivered_mwh: float
    incentive_won: float
    energy_cost_won: float
    recovery_won: float
    degradation_won: float
    peak_penalty_won: float = 0.0     # DR 충전으로 기본요금이 오르는 위험비용

    @property
    def net_won(self) -> float:
        return (self.incentive_won - self.energy_cost_won
                + self.recovery_won - self.degradation_won - self.peak_penalty_won)

    @property
    def delivery_rate(self) -> float:
        return self.delivered_mwh / self.cleared_mwh if self.cleared_mwh > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "cleared_mwh": round(self.cleared_mwh, 2),
            "delivered_mwh": round(self.delivered_mwh, 2),
            "delivery_rate": round(self.delivery_rate, 3),
            "incentive_won": round(self.incentive_won),
            "energy_cost_won": round(self.energy_cost_won),
            "recovery_won": round(self.recovery_won),
            "degradation_won": round(self.degradation_won),
            "peak_penalty_won": round(self.peak_penalty_won),
            "net_won": round(self.net_won),
        }


def settle_event(cleared_mwh: float, delivery_rate: float, fleet: Fleet,
                 incentive_won_per_kwh: float, hour: int = 13,
                 recovery_ratio: float = 0.8,
                 peak_managed: bool = False,
                 month_peak_risk: float = 0.35) -> Settlement:
    """이벤트 1회 정산.

    hour           이벤트 시각 — 요금 단가와 피크 위험을 결정한다
    peak_managed   피크 예약 엔진으로 계량기 피크를 관리하는가.
                   True면 여유 있는 단지에만 충전을 배분해 기본요금 상승을 막는다.
    month_peak_risk 관리하지 않을 때 그달 최대수요를 갱신할 확률
    recovery_ratio 흡수한 전기 중 나중에 실제로 활용하는 비율
    """
    delivered = cleared_mwh * max(0.0, min(1.0, delivery_rate))
    kwh = delivered * 1000.0

    incentive = kwh * incentive_won_per_kwh
    energy_cost = kwh * tou_at(hour)                      # 경부하가 아니다
    usable = kwh * fleet.eff_charge * recovery_ratio
    recovery = usable * TOU_PEAK
    degradation = usable * fleet.degradation_won

    # 피크 위험 — DR 충전이 계량기 최대수요를 밀어 올리면 기본요금이 오른다.
    # 피크 예약 엔진이 있으면 여유 있는 단지로 분산해 이 비용을 거의 없앤다.
    penalty = 0.0
    if is_peak_hour(hour) and not peak_managed:
        added_kw = delivered * 1000.0            # 1시간 이벤트 → kWh ≈ kW
        penalty = added_kw * BASE_RATE_WON_PER_KW * month_peak_risk

    return Settlement(cleared_mwh, delivered, incentive, energy_cost,
                      recovery, degradation, penalty)


def breakeven_incentive(fleet: Fleet, hour: int = 13,
                        recovery_ratio: float = 0.8,
                        peak_managed: bool = True) -> float:
    """인센티브가 얼마 이상이어야 참여가 성립하는가 (₩/kWh).

    정산 단가가 공개돼 있지 않으므로 **가정하는 대신 조건을 제시한다.**
    이 값보다 낮으면 참여할수록 손해다.
    """
    per_kwh_recovery = fleet.eff_charge * recovery_ratio * (TOU_PEAK - fleet.degradation_won)
    cost = tou_at(hour)
    if is_peak_hour(hour) and not peak_managed:
        cost += BASE_RATE_WON_PER_KW * 0.35      # 피크 갱신 위험비용
    return max(0.0, cost - per_kwh_recovery)


# ══════════════════════════════════════════════════════════════
#  참여 전략
# ══════════════════════════════════════════════════════════════

class Baseline:
    """기존 시장 참여자 — 공장·건물. 실측 이행률을 그대로 따른다.

    낙찰은 받지만 절반 이상 못 지킨다. 쓸 데가 없어서다.
    """

    name = "market_baseline"
    label = "기존 참여자 (공장·건물)"
    description = "실측 이행률 41.7% · 중앙값 21.2% — 지시받아도 쓸 데가 없다"
    peak_managed = False        # 피크 상승을 계산·회피할 수단이 없다

    def __init__(self, facts: dict) -> None:
        self.facts = facts

    def bid_mwh(self, fleet: Fleet, request_mwh: float) -> float:
        return min(request_mwh, fleet.usable_mwh)

    def delivery(self, rng: random.Random) -> float:
        """실측 분포를 재현 — 평균 41.7%, 중앙값 21.2%로 강하게 우편향."""
        # 로그정규 형태로 낮은 값에 몰리고 가끔 100%를 달성하는 분포
        v = rng.lognormvariate(math.log(0.21), 0.95)
        return max(0.0, min(1.0, v))


class BatteryFleet(Baseline):
    """배터리 포트폴리오 — 시키면 한다.

    충전 버튼을 누르는 것이 전부이므로 이행률이 구조적으로 높다.
    남는 리스크는 통신 두절·고장·SOC 부족뿐이고, 그것도 여러 단지로 분산된다.
    """

    name = "battery_fleet"
    label = "배터리 포트폴리오 (피크 미관리)"
    description = "이행률 97% — 지시 즉시 이행. 다만 피크 상승 위험은 방치"
    peak_managed = False

    def delivery(self, rng: random.Random) -> float:
        # 단지별 성공 여부를 이항으로 굴려 분산 효과를 반영
        n = 20
        ok = sum(1 for _ in range(n) if rng.random() < 0.985)
        return min(1.0, (ok / n) * 1.0) * (0.96 + 0.04 * rng.random())


class ConservativeFleet(BatteryFleet):
    """보수적 입찰 — 확실히 이행 가능한 양만 응찰한다.

    이행률이 정산·평판에 직결되는 시장에서는 **덜 받고 다 지키는 편**이
    많이 받고 못 지키는 것보다 낫다. 미이행은 다음 낙찰에 불이익이 된다.
    """

    name = "conservative_fleet"
    label = "배터리 + 피크 예약 (PeakBridge)"
    description = "여유 있는 단지에만 충전 배분 — 이행하면서 기본요금도 안 올린다"
    peak_managed = True         # 피크 예약 엔진이 계량기 상승을 막는다

    def bid_mwh(self, fleet: Fleet, request_mwh: float) -> float:
        return min(request_mwh, fleet.usable_mwh * 0.7)


def registry() -> dict:
    return {c.name: c for c in (Baseline, BatteryFleet, ConservativeFleet)}


# ══════════════════════════════════════════════════════════════
#  시뮬레이션
# ══════════════════════════════════════════════════════════════

@dataclass
class YearResult:
    strategy: str
    label: str
    events: int
    cleared_mwh: float
    delivered_mwh: float
    net_won: float
    settlements: list[dict] = field(default_factory=list)

    @property
    def delivery_rate(self) -> float:
        return self.delivered_mwh / self.cleared_mwh if self.cleared_mwh > 0 else 0.0


def simulate_year(strategy, fleet: Fleet, facts: dict,
                  incentive_won_per_kwh: float, seed: int = 11) -> YearResult:
    """1년치 플러스 DR 참여 시뮬레이션.

    이벤트 발생 빈도·시각·규모는 **실측 통계**에서 가져온다.
    """
    rng = random.Random(seed)
    events = int(round(facts["event_days_per_year"]))
    per_event = facts["avg_cleared_per_event_mwh"]

    cleared_t = delivered_t = net_t = 0.0
    hours = facts.get("event_hours") or [13]
    managed = getattr(strategy, "peak_managed", False)
    rows = []
    for _ in range(max(1, events)):
        # 거래소가 요청하는 증대량 (실측 평균 주변에서 변동)
        request = max(0.5, rng.gauss(per_event, per_event * 0.5))
        hour = rng.choice(hours)                       # 실측 이벤트 시간대
        bid = strategy.bid_mwh(fleet, request)
        cleared = bid * facts["clearing_rate"]          # 실측 낙찰률 100%
        s = settle_event(cleared, strategy.delivery(rng), fleet,
                         incentive_won_per_kwh, hour=hour, peak_managed=managed)
        cleared_t += s.cleared_mwh
        delivered_t += s.delivered_mwh
        net_t += s.net_won
        rows.append(s.to_dict())

    return YearResult(
        strategy=strategy.name, label=strategy.label, events=events,
        cleared_mwh=round(cleared_t, 1), delivered_mwh=round(delivered_t, 1),
        net_won=round(net_t), settlements=rows,
    )


def compare(fleet: Fleet | None = None,
            incentive_won_per_kwh: float = 120.0,
            seed: int = 11) -> dict:
    """전략 비교 + 손익분기 + 실측 근거를 한 번에."""
    f = fleet or Fleet()
    facts = load_facts()
    be_managed = breakeven_incentive(f, hour=13, peak_managed=True)
    be_raw = breakeven_incentive(f, hour=13, peak_managed=False)

    rows = []
    for cls in registry().values():
        r = simulate_year(cls(facts), f, facts, incentive_won_per_kwh, seed)
        rows.append({
            "strategy": r.strategy, "label": r.label,
            "description": cls.description,
            "events": r.events,
            "cleared_mwh": r.cleared_mwh,
            "delivered_mwh": r.delivered_mwh,
            "delivery_rate": round(r.delivery_rate, 3),
            "net_won": r.net_won,
        })
    rows.sort(key=lambda x: -x["net_won"])

    base = next((x for x in rows if x["strategy"] == "market_baseline"), None)
    best = rows[0]
    edge = (best["delivery_rate"] - base["delivery_rate"]) if base else None

    return {
        "market": "제주 플러스 DR (수요증대 DR)",
        "facts": facts,
        "assumption": {
            "incentive_won_per_kwh": incentive_won_per_kwh,
            "tou_peak_won": TOU_PEAK,
            "tou_off_won": TOU_OFF,
            "base_rate_won_per_kw": BASE_RATE_WON_PER_KW,
            "breakeven_managed": round(be_managed, 1),
            "breakeven_unmanaged": round(be_raw, 1),
            "note": (
                "플러스 DR 정산 단가는 공개 데이터에 없다. 위 인센티브는 가정값이다. "
                f"피크를 관리하면 손익분기 ₩{be_managed:.0f}/kWh, "
                f"관리하지 않으면 ₩{be_raw:,.0f}/kWh 다. "
                "이벤트가 최대부하 시간대(11~16시)에 몰려 있어, 피크 관리 없이는 "
                "기본요금 상승이 인센티브를 압도한다."
            ),
        },
        "fleet": {
            "sites": f.sites, "power_mw": round(f.power_mw, 1),
            "usable_mwh": round(f.usable_mwh, 1),
        },
        "leaderboard": rows,
        "edge": {
            "baseline_delivery": base["delivery_rate"] if base else None,
            "ours_delivery": best["delivery_rate"],
            "gap": round(edge, 3) if edge is not None else None,
        },
        "thesis": (
            f"낙찰률 {facts['clearing_rate'] * 100:.0f}% — 입찰하면 전부 낙찰된다. 경쟁이 없다. "
            f"이행률 {facts['delivery_rate'] * 100:.1f}% — 낙찰자도 지키지 못한다. "
            "우리가 파는 것은 전기가 아니라 이행 확실성이다."
        ),
        "disclaimer": (
            "이벤트 빈도·낙찰률·이행률·SMP는 전력거래소 실측(2021~2023, 272건)이다. "
            "정산 단가와 우리 자원의 이행률은 가정이며, 실증으로 검증해야 한다."
        ),
    }

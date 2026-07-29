"""제주 운영 시뮬레이터 — 플러스DR 발령에 실제로 대응해 보는 엔진.

── 무엇을 시뮬레이션하는가 ────────────────────────────────────

제주에서 우리가 하려는 일을 그대로 재현한다.

    1. 재생에너지 과잉 → 전력거래소가 출력제어를 건다
    2. 동시에 "전기를 더 써달라"는 플러스DR이 발령된다
    3. 우리는 보유 단지 중 **어디에 얼마나 충전시킬지** 정해야 한다
    4. 실제로 이행되고, 정산된다

── 이 시뮬레이터가 증명하려는 것 ─────────────────────────────

핵심은 3번이다. 그냥 모든 단지에 똑같이 시키면 안 된다.

    플러스DR 발령 시각 = 낮 11~16시 = **최대부하 시간대**
    → 그 시간에 충전하면 계량기 피크가 올라간다
    → 기본요금은 그달 최고 순간 하나로 정해진다
    → DR로 번 돈보다 오른 기본요금이 더 클 수 있다

그래서 **"지금 피크를 올리지 않고 충전할 수 있는 여유"**를 단지별로 계산해
여유가 있는 곳에만 배정해야 한다. 그 계산이 우리 상품이다.

시뮬레이터는 두 방식을 나란히 돌려 차이를 보여준다.
    even  — 균등 배분 (여유를 안 봄)
    peak  — 피크 여유 기반 배분 (우리 방식)

── 실측 근거 ──────────────────────────────────────────────────

이벤트 발생 패턴은 전력거래소 공개 데이터에서 가져온다.
    출력제어  2021~2024 · 335일 · 73,224MWh · 13~15시 집중 · 봄가을
    플러스DR  2021~2023 · 272건 · 낙찰률 100% · 이행률 41.7%

※ 정산 단가만 미공개라 가정값을 쓴다. 화면에 손익분기와 함께 표기한다.
※ 상태는 메모리에만 둔다(서버 재시작 시 초기화).
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
FACTS = Path(__file__).resolve().parents[2] / "data" / "jeju_facts.json"

# 계시별 요금 (₩/kWh) — 실증 단지 고지서로 교체해야 하는 근사값
TOU_OFF, TOU_MID, TOU_PEAK = 70.0, 110.0, 180.0
BASE_RATE = 8_320.0        # 기본요금 ₩/kW·월
DEG = 50.0                 # 배터리 열화 ₩/kWh
ESS_CAPEX_PER_KWH = 300_000.0   # ESS 설치 단가 가정 ₩/kWh (그릇값)
EFF_C = 0.95               # 충전 효율


def tou(hour: int) -> float:
    if hour < 9 or hour >= 23:
        return TOU_OFF
    if 10 <= hour < 12 or 13 <= hour < 19:
        return TOU_PEAK
    return TOU_MID


def is_peak_hour(hour: int) -> bool:
    return 10 <= hour < 12 or 13 <= hour < 19


# ══════════════════════════════════════════════════════════════
#  자원 (단지)
# ══════════════════════════════════════════════════════════════

@dataclass
class Site:
    """참여 단지 하나."""

    id: str
    name: str
    contract_kw: float          # 계약전력
    capacity_kwh: float         # 배터리 용량
    power_kw: float             # 충·방전 정격
    soc: float                  # 현재 잔량 (0~1)
    today_peak_kw: float        # 오늘 지금까지 최대수요
    month_peak_kw: float        # 이번 달 최대수요
    base_load_kw: float         # 지금 이 시각의 기본 부하
    online: bool = True         # 통신 정상 여부
    live: bool = False          # 실측 자원 여부 (차주 예약 유연성)

    # ── 계산 속성 ──
    @property
    def room_kwh(self) -> float:
        """더 채울 수 있는 에너지."""
        return max(0.0, (0.95 - self.soc) * self.capacity_kwh)

    def peak_headroom_kw(self) -> float:
        """지금 충전해도 '그달 기본요금'을 안 올리는 여유 (kW).

        기준선은 계약전력과 이번 달 최대수요 중 **높은 쪽**이다.
        이미 250kW를 찍었다면 그 아래로는 더 써도 청구액이 안 오른다.
        """
        guard = max(self.contract_kw, self.month_peak_kw)
        return max(0.0, guard - self.base_load_kw)

    def max_charge_kw(self) -> float:
        """지금 안전하게 걸 수 있는 충전 출력."""
        if not self.online:
            return 0.0
        return min(self.power_kw, self.room_kwh, self.peak_headroom_kw())

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "contract_kw": round(self.contract_kw),
            "capacity_kwh": round(self.capacity_kwh),
            "soc": round(self.soc, 3),
            "room_kwh": round(self.room_kwh, 1),
            "base_load_kw": round(self.base_load_kw, 1),
            "today_peak_kw": round(self.today_peak_kw, 1),
            "month_peak_kw": round(self.month_peak_kw, 1),
            "headroom_kw": round(self.peak_headroom_kw(), 1),
            "max_charge_kw": round(self.max_charge_kw(), 1),
            "online": self.online,
            "live": self.live,
        }


def make_fleet(n: int = 12, seed: int = 5) -> list[Site]:
    """시연용 단지 구성 — 여유가 제각각이어야 배분의 의미가 드러난다."""
    rng = random.Random(seed)
    names = ["한라뷰", "애월그린", "노형센트럴", "서귀포아뜰", "삼양파크",
             "연동스카이", "이도힐스", "화북마린", "조천숲", "표선베이",
             "성산이스트", "대정웨스트"]
    out = []
    for i in range(min(n, len(names))):
        contract = rng.choice([150.0, 200.0, 250.0, 300.0])
        # 이번 달 최대수요 — 계약전력 대비 제각각
        mpeak = contract * rng.uniform(0.75, 1.12)
        base = contract * rng.uniform(0.42, 0.88)      # 지금 부하
        out.append(Site(
            id=f"JJ{i + 1:02d}", name=names[i],
            contract_kw=contract,
            capacity_kwh=rng.choice([120.0, 180.0, 240.0]),
            power_kw=rng.choice([40.0, 60.0, 80.0]),
            soc=rng.uniform(0.18, 0.62),
            today_peak_kw=base * rng.uniform(1.0, 1.25),
            month_peak_kw=mpeak,
            base_load_kw=base,
            online=rng.random() > 0.08,                # 약 8% 통신 두절
        ))
    return out


# ══════════════════════════════════════════════════════════════
#  이벤트
# ══════════════════════════════════════════════════════════════

def _load_facts() -> dict:
    try:
        d = json.loads(FACTS.read_text(encoding="utf-8"))
        pdr = d.get("plus_dr", {})
        cur = d.get("curtailment", {})
        return {
            "clearing_rate": pdr.get("clearing_rate", 1.0),
            "market_delivery": pdr.get("delivery_rate", 0.417),
            "delivery_median": pdr.get("delivery_pct_median", 15.8),
            "avg_cleared_mwh": round(
                (pdr.get("cleared_mwh") or 1444.5) / max(pdr.get("records") or 272, 1), 2),
            "event_hours": sorted(int(h) for h in (pdr.get("hour_hist") or {11: 1})) or [13],
            "curtail_days_per_year": cur.get("days_per_year", 86.0),
            "curtail_hours": cur.get("top_hours", [13, 14, 12, 15]),
            "loaded": True,
        }
    except Exception:  # noqa: BLE001
        return {"clearing_rate": 1.0, "market_delivery": 0.417, "delivery_median": 15.8,
                "avg_cleared_mwh": 5.31, "event_hours": [11, 12, 13, 14, 15, 16],
                "curtail_days_per_year": 86.0, "curtail_hours": [13, 14, 12, 15],
                "loaded": False}


@dataclass
class Event:
    """플러스DR 발령 1건."""

    ts: str
    hour: int
    request_mwh: float           # 거래소 요청 증대량
    curtail_mw: float            # 동시에 걸린 출력제어 규모
    duration_min: int = 60
    status: str = "open"         # open | dispatched | settled

    def to_dict(self) -> dict:
        return {
            "ts": self.ts, "hour": self.hour,
            "request_mwh": round(self.request_mwh, 2),
            "request_kwh": round(self.request_mwh * 1000),
            "curtail_mw": round(self.curtail_mw, 1),
            "duration_min": self.duration_min,
            "status": self.status,
            "tou_won": tou(self.hour),
            "is_peak_hour": is_peak_hour(self.hour),
        }


# ══════════════════════════════════════════════════════════════
#  배분 · 이행 · 정산
# ══════════════════════════════════════════════════════════════

def allocate(sites: list[Site], need_kwh: float, mode: str, hour: int) -> list[dict]:
    """요청량을 단지에 배분한다.

    mode = "peak"  피크 여유가 큰 단지부터 (우리 방식)
    mode = "even"  모든 단지에 균등 배분 (여유를 안 봄 — 대조군)
    """
    live = [s for s in sites if s.online]
    plans: list[dict] = []

    if mode == "even":
        # 여유를 보지 않고 정격까지 균등하게 건다.
        # 배터리 용량과 통신만 보고, 계량기 피크는 고려하지 않는다.
        share = need_kwh / max(len(live), 1)
        for s in live:
            kw = min(s.power_kw, s.room_kwh, share)
            if kw > 0.5:
                plans.append({"site": s.id, "charge_kw": round(kw, 1)})
        return plans

    # peak — 피크를 올리지 않는 범위 안에서, 여유가 큰 곳부터 채운다
    order = sorted(live, key=lambda s: -s.max_charge_kw())
    left = need_kwh
    for s in order:
        if left <= 0.5:
            break
        kw = min(s.max_charge_kw(), left)
        if kw > 0.5:
            plans.append({"site": s.id, "charge_kw": round(kw, 1)})
            left -= kw
    return plans


def execute(sites: list[Site], plans: list[dict], hour: int,
            incentive: float, rng: random.Random) -> dict:
    """계획을 실행하고 결과를 계산한다.

    반환에는 이행률뿐 아니라 **기본요금 영향**이 함께 들어간다.
    이행만 잘하고 피크를 올리면 결과적으로 손해이기 때문이다.
    """
    by_id = {s.id: s for s in sites}
    rows = []
    ordered_kwh = delivered_kwh = 0.0
    energy_cost = incentive_won = peak_penalty = recovery = degradation = 0.0

    for p in plans:
        s = by_id.get(p["site"])
        if s is None:
            continue
        ordered = float(p["charge_kw"])          # 1시간 이벤트 → kW ≈ kWh
        ordered_kwh += ordered

        # 실제 이행 — 배터리는 지시받으면 거의 그대로 한다.
        # 남는 불확실성은 통신·잔여용량·현장 상황.
        cap = min(s.room_kwh, s.power_kw)
        actual = min(ordered, cap) * rng.uniform(0.95, 1.0)
        delivered_kwh += actual

        # 이 충전이 계량기 피크를 올리는가
        new_load = s.base_load_kw + actual
        guard = max(s.contract_kw, s.month_peak_kw)
        over_kw = max(0.0, new_load - guard)
        pen = over_kw * BASE_RATE                # 그달 내내 적용되는 비용
        peak_penalty += pen

        energy_cost += actual * tou(hour)
        incentive_won += actual * incentive
        stored = actual * EFF_C * 0.8            # 나중에 실제 활용되는 분
        recovery += stored * TOU_PEAK
        degradation += stored * DEG

        rows.append({
            "site": s.id, "name": s.name,
            "ordered_kw": round(ordered, 1),
            "delivered_kw": round(actual, 1),
            "rate": round(actual / ordered, 3) if ordered > 0 else 0.0,
            "load_before_kw": round(s.base_load_kw, 1),
            "load_after_kw": round(new_load, 1),
            "guard_kw": round(guard, 1),
            "peak_over_kw": round(over_kw, 1),
            "peak_penalty_won": round(pen),
        })

        # 상태 갱신
        s.soc = min(0.95, s.soc + actual * EFF_C / s.capacity_kwh)
        s.today_peak_kw = max(s.today_peak_kw, new_load)
        s.month_peak_kw = max(s.month_peak_kw, new_load)

    net = incentive_won - energy_cost + recovery - degradation - peak_penalty
    return {
        "rows": rows,
        "ordered_kwh": round(ordered_kwh, 1),
        "delivered_kwh": round(delivered_kwh, 1),
        "delivery_rate": round(delivered_kwh / ordered_kwh, 3) if ordered_kwh > 0 else 0.0,
        "incentive_won": round(incentive_won),
        "energy_cost_won": round(energy_cost),
        "recovery_won": round(recovery),
        "degradation_won": round(degradation),
        "peak_penalty_won": round(peak_penalty),
        "net_won": round(net),
        "sites_over_peak": sum(1 for r in rows if r["peak_over_kw"] > 0),
    }


# ══════════════════════════════════════════════════════════════
#  시뮬레이터 (in-memory)
# ══════════════════════════════════════════════════════════════

class JejuSim:
    """제주 운영 시뮬레이터 — 서버 메모리에만 상태를 둔다."""

    def __init__(self) -> None:
        self.facts = _load_facts()
        self.sites: list[Site] = make_fleet()
        self.event: Event | None = None
        self.log: list[dict] = []
        self.history: list[dict] = []
        self._rng = random.Random(17)
        self._snapshot: list[dict] | None = None

    # ── 실측 자원 (차주 예약 유연성) ──
    def _live_site(self) -> Site | None:
        """폰(/drive)에서 실제로 예약된 '알뜰 충전' 유연성을 자원 한 줄로 만든다.

        가상 단지 12곳과 달리 이 자원만 실데이터다. 재고가 0이면 목록에서 빠진다
        (예약이 없을 때 0kWh 자원이 떠서 화면이 어색해지는 것 방지).

        피크 제약을 따로 두지 않는 이유: 유연성 재고는 이미 '미룰 수 있는 양'으로
        산정된 값이라, 여기에 또 기본요금 여유를 곱하면 이중 차감이 된다.
        """
        try:
            from app.services.flex_service import flex_service

            flex = flex_service.flexibility("building-A")
        except Exception:  # noqa: BLE001
            return None

        kwh = float(flex.get("flex_kwh") or 0.0)
        if kwh <= 0.1:
            return None
        n = max(1, int(flex.get("flex_session_count") or 1))
        power = 7.0 * n          # 완속 충전기 7kW × 예약 대수
        return Site(
            id="LIVE-EV", name="차주 유연성",
            contract_kw=power, capacity_kwh=kwh / 0.95, power_kw=power,
            soc=0.0, today_peak_kw=0.0, month_peak_kw=power, base_load_kw=0.0,
            online=True, live=True,
        )

    def _all_sites(self) -> list[Site]:
        """가상 단지 + (있으면) 실측 차주 유연성."""
        live = self._live_site()
        return self.sites + ([live] if live else [])

    # ── 상태 ──
    def state(self) -> dict:
        sites = self._all_sites()
        total_room = sum(s.room_kwh for s in sites if s.online)
        total_head = sum(s.max_charge_kw() for s in sites if s.online)
        return {
            "facts": self.facts,
            "sites": [s.to_dict() for s in sites],
            "event": self.event.to_dict() if self.event else None,
            "fleet": {
                "count": len(sites),
                "online": sum(1 for s in sites if s.online),
                "room_kwh": round(total_room, 1),
                "safe_charge_kw": round(total_head, 1),
                "avg_soc": round(sum(s.soc for s in sites) / max(len(sites), 1), 3),
            },
            "log": self.log[:20],
            "history": self.history[-10:],
        }

    def _say(self, level: str, msg: str) -> None:
        self.log.insert(0, {
            "ts": datetime.now(KST).strftime("%H:%M:%S"),
            "level": level, "msg": msg,
        })
        del self.log[40:]

    # ── 이벤트 발령 ──
    def raise_event(self, hour: int | None = None,
                    request_mwh: float | None = None) -> dict:
        """플러스DR 발령. 시각·규모는 실측 분포에서 뽑는다."""
        h = hour if hour is not None else self._rng.choice(self.facts["event_hours"])
        base = self.facts["avg_cleared_mwh"]
        req = request_mwh if request_mwh is not None else max(
            0.5, self._rng.gauss(base, base * 0.4))
        # 출력제어 규모는 실측 일평균(약 218MWh/일)을 시간 단위로 환산
        curt = max(10.0, self._rng.gauss(45.0, 15.0))

        self.event = Event(
            ts=datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
            hour=h, request_mwh=req, curtail_mw=curt,
        )
        self._snapshot = [s.to_dict() for s in self._all_sites()]
        self._say("warn",
                  f"플러스DR 발령 — {h}시 · 요청 {req * 1000:,.0f}kWh · "
                  f"출력제어 {curt:.0f}MW · {'최대부하' if is_peak_hour(h) else '경부하'} 시간대")
        return self.state()

    # ── 배분 계획 (실행 전 미리보기) ──
    def plan(self, mode: str = "peak") -> dict:
        if self.event is None:
            return {"error": "발령된 이벤트가 없습니다"}
        need = self.event.request_mwh * 1000
        plans = allocate(self._all_sites(), need, mode, self.event.hour)
        total = sum(p["charge_kw"] for p in plans)
        return {
            "mode": mode,
            "need_kwh": round(need),
            "planned_kw": round(total, 1),
            "coverage": round(total / need, 3) if need > 0 else 0.0,
            "sites_used": len(plans),
            "plans": plans,
        }

    # ── 실행 ──
    def dispatch(self, mode: str = "peak", incentive: float = 120.0) -> dict:
        if self.event is None:
            return {"error": "발령된 이벤트가 없습니다"}

        need = self.event.request_mwh * 1000
        sites = self._all_sites()
        plans = allocate(sites, need, mode, self.event.hour)
        result = execute(sites, plans, self.event.hour, incentive, self._rng)
        result["mode"] = mode
        result["need_kwh"] = round(need)
        result["coverage"] = round(result["delivered_kwh"] / need, 3) if need > 0 else 0.0
        result["incentive_assumed"] = incentive
        result["market_delivery_rate"] = self.facts["market_delivery"]

        self.event.status = "settled"
        self.history.append({
            "ts": self.event.ts, "hour": self.event.hour, "mode": mode,
            "delivery_rate": result["delivery_rate"],
            "net_won": result["net_won"],
            "peak_penalty_won": result["peak_penalty_won"],
        })

        label = "피크 여유 기반" if mode == "peak" else "균등 배분"
        lv = "ok" if result["net_won"] > 0 else "crit"
        self._say(lv,
                  f"급전 완료 ({label}) — 이행 {result['delivery_rate'] * 100:.0f}% · "
                  f"순손익 ₩{result['net_won']:,} · "
                  f"피크 초과 단지 {result['sites_over_peak']}곳")
        return result

    # ── 두 방식 나란히 비교 (시연용) ──
    def compare(self, incentive: float = 120.0) -> dict:
        """같은 이벤트를 두 방식으로 각각 실행해 결과를 대조한다.

        상태를 훼손하면 안 되므로 자원을 복제해서 돌린다.
        """
        if self.event is None:
            return {"error": "발령된 이벤트가 없습니다"}

        need = self.event.request_mwh * 1000
        out = {}
        for mode in ("even", "peak"):
            clone = [Site(**{k: v for k, v in s.__dict__.items()}) for s in self._all_sites()]
            plans = allocate(clone, need, mode, self.event.hour)
            r = execute(clone, plans, self.event.hour, incentive, random.Random(99))
            r["coverage"] = round(r["delivered_kwh"] / need, 3) if need > 0 else 0.0
            out[mode] = r

        gap = out["peak"]["net_won"] - out["even"]["net_won"]
        return {
            "need_kwh": round(need),
            "hour": self.event.hour,
            "is_peak_hour": is_peak_hour(self.event.hour),
            "incentive_assumed": incentive,
            "even": out["even"],
            "peak": out["peak"],
            "gap_won": round(gap),
            "verdict": (
                f"같은 요청, 같은 자원인데 배분 방식만으로 ₩{gap:,.0f} 차이. "
                f"균등 배분은 {out['even']['sites_over_peak']}개 단지의 기본요금을 올려 "
                f"₩{out['even']['peak_penalty_won']:,.0f}을 잃었다."
            ),
        }

    # ── 자산 방식 대조 (ESS 직접 구매 vs EV 연계) ──
    def compare_assets(self, incentive: float = 120.0,
                       ev_discount: float = 40.0) -> dict:
        """같은 플러스DR 요청을 두 가지 자산으로 흡수했을 때를 대조한다.

        ── 이 화면이 답하는 질문 ──────────────────────────────

            "버려지는 전기가 공짜라면, ESS를 잔뜩 사서 받아두면 되지 않나?"

        답은 '안 된다'이다. 전기는 공짜여도 **그릇이 공짜가 아니기 때문**이다.
        배터리를 새로 사면 그 값(CAPEX)과 열화비용을 우리가 전부 진다.

        반면 전기차는 **차주가 이미 산 배터리**다. 우리는 그릇을 사지 않고,
        충전 시점을 위임받는 대가로 요금을 할인해 준다. 열화는 차주 몫이며
        할인이 그 대가다. 그래서 같은 흡수량이라도 수지가 뒤집힌다.

        ※ 그릇값·할인율은 가정값이다(화면에 표기). 흡수 물리량과
          기본요금 영향은 동일한 엔진(execute)으로 계산해 조건을 맞춘다.
        """
        if self.event is None:
            return {"error": "발령된 이벤트가 없습니다"}

        need = self.event.request_mwh * 1000
        hour = self.event.hour

        # 두 방식 모두 '피크 여유 기반'으로 배분해 배분 알고리즘 차이를 제거한다.
        clone = [Site(**{k: v for k, v in s.__dict__.items()}) for s in self._all_sites()]
        plans = allocate(clone, need, "peak", hour)
        base = execute(clone, plans, hour, incentive, random.Random(99))
        absorbed = base["delivered_kwh"]

        # ── ESS 직접 구매 ────────────────────────────────────
        # 흡수량을 담으려면 그만큼의 배터리를 사야 한다.
        # 사이클당 가용 구간(SOC 15~95%)을 고려해 필요한 정격 용량을 잡는다.
        need_capacity_kwh = absorbed / 0.8 if absorbed > 0 else 0.0
        capex = need_capacity_kwh * ESS_CAPEX_PER_KWH
        # 연간 수익: 실측 출력제어 빈도만큼만 이벤트가 반복된다.
        events_per_year = self.facts.get("curtail_days_per_year", 86.0)
        ess_year_net = base["net_won"] * events_per_year
        ess_payback = (capex / ess_year_net) if ess_year_net > 0 else None

        # ── EV 연계 ──────────────────────────────────────────
        # 그릇값 0. 열화는 차주 부담이며, 그 대가로 요금을 할인한다.
        discount_cost = absorbed * ev_discount
        ev_net = (base["net_won"]
                  + base["degradation_won"]      # 우리가 지지 않는 비용 → 되돌림
                  - discount_cost)               # 대신 할인을 부담
        ev_year_net = ev_net * events_per_year

        return {
            "absorbed_kwh": round(absorbed, 1),
            "events_per_year": round(events_per_year, 1),
            "incentive_assumed": incentive,
            "ev_discount_assumed": ev_discount,
            "capex_per_kwh_assumed": ESS_CAPEX_PER_KWH,
            "ess_owned": {
                "label": "ESS 직접 구매",
                "capex_won": round(capex),
                "need_capacity_kwh": round(need_capacity_kwh, 1),
                "degradation_won": base["degradation_won"],
                "event_net_won": base["net_won"],
                "year_net_won": round(ess_year_net),
                "payback_years": round(ess_payback, 1) if ess_payback else None,
            },
            "ev_fleet": {
                "label": "EV 연계 (차주 배터리)",
                "capex_won": 0,
                "need_capacity_kwh": 0.0,
                "discount_cost_won": round(discount_cost),
                "event_net_won": round(ev_net),
                "year_net_won": round(ev_year_net),
                "payback_years": 0.0,
            },
            "verdict": (
                f"같은 {absorbed:,.0f}kWh를 흡수하는데, ESS를 사면 "
                f"₩{capex:,.0f}이 먼저 나간다. 회수에 "
                f"{f'{ess_payback:,.0f}년' if ess_payback else '수익 없음'}. "
                f"전기차는 그릇값이 0원이라 첫 이벤트부터 흑자다."
            ),
            "note": "그릇값·할인율은 가정값 · 흡수 물리량과 기본요금 영향은 동일 엔진 계산",
        }

    # ── 초기화 ──
    def reset(self, sites: int = 12) -> dict:
        self.sites = make_fleet(sites)
        self.event = None
        self.history.clear()
        self.log.clear()
        self._say("info", f"시뮬레이터 초기화 — 단지 {sites}곳")
        return self.state()

    def advance(self) -> dict:
        """한 시간 진행 — 부하가 바뀌고 배터리가 자연 소모된다."""
        for s in self.sites:
            s.base_load_kw = max(20.0, s.base_load_kw * self._rng.uniform(0.88, 1.15))
            s.soc = max(0.1, s.soc - self._rng.uniform(0.0, 0.03))
            s.today_peak_kw = max(s.today_peak_kw, s.base_load_kw)
            if self._rng.random() < 0.05:
                s.online = not s.online
        self._say("info", "1시간 경과 — 부하·잔량 갱신")
        return self.state()


jeju_sim = JejuSim()

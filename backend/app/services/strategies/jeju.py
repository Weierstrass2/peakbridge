"""제주 실시간시장 전용 트레이딩 엔진.

── 왜 제주를 따로 다루는가 ─────────────────────────────────────

육지 SMP로 차익거래를 백테스트하면 **구조적으로 적자다.**

    일중 최저 SMP  42.5원  →  충전단가 ÷ 효율 0.9 = 47.2원
    배터리 열화                                  + 50.0원
    ─────────────────────────────────────────────────────
    변동비                                        97.2원
    일중 최고 SMP  90.1원  →  마진 -7.1원/kWh

"싸게 사서 비싸게 판다"가 성립하지 않는다. 스프레드(47.6원)가 열화비용(50원)보다
작기 때문이다. 이건 전략을 잘 짜서 해결되는 문제가 아니라 **시장 구조의 문제**다.

제주는 이 등식이 뒤집힌다. 이유는 하나다:

    제주에는 **버려지는 전력**이 있다.

재생에너지 설비가 수요 대비 과도해, 봄·가을 낮이나 바람이 센 새벽에는
순부하(수요 − 재생출력)가 경직성 전원의 최소출력보다 낮아진다.
이때 계통은 재생에너지 출력제어(curtailment)를 건다 — 즉 **전기를 버린다.**

버려지는 전력의 가격은 0에 수렴한다. 그러면 우리 변동비는

    충전단가 0 ÷ 0.9 + 열화 50 = **50원**

이 되고, 같은 90원에 팔아도 마진이 **+40원/kWh**로 뒤집힌다.

── 그래서 제주에서 우리가 파는 상품은 '차익거래'가 아니다 ────────

    육지: "싼 시간에 사서 비싼 시간에 판다"          → 스프레드 장사, 안 됨
    제주: "버릴 전력을 받아주고, 모자란 시간에 낸다"  → 흡수 서비스, 됨

발전사업자는 출력제어를 당하면 그 발전량이 통째로 손실이다.
우리가 받아주면 그들은 손실을 줄이고, 우리는 연료를 공짜로 얻는다.
**한쪽의 폐기물이 다른 쪽의 원료가 되는 구조** — 이게 제주의 진짜 알파다.

── 이 파일이 모델링하는 것 ─────────────────────────────────────

  1. 순부하(net load) = 수요 − 태양광 − 풍력
  2. 순부하가 최소출력 아래로 내려가면 → 출력제어 → 가격 0 (또는 음수)
  3. 실시간 가격은 순부하에 볼록(convex)하게 반응한다
     — 여유가 없을수록 가파르게 오른다
  4. 하루전(DA) 예측은 **재생 예측오차** 때문에 실시간(RT)과 벌어진다
     → 이 괴리(basis)가 두 번째 알파원이다

주의 — 정직성 고지:
    제주 실시간시장 15분 체결가의 공개 시계열은 확보하지 못했다.
    여기 가격은 **위 물리 메커니즘으로 생성한 모델**이며 실측이 아니다.
    EPSIS 시간별 제주 SMP를 확보하면 calibrate()로 수준·변동성을 맞출 수 있다.
    화면·발표에서는 반드시 '모델'로 표기한다.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import numpy as np

SLOTS = 96          # 15분 × 96 = 24시간
SLOT_H = 0.25       # 슬롯당 시간


# ══════════════════════════════════════════════════════════════
#  시장 모델
# ══════════════════════════════════════════════════════════════

@dataclass
class JejuMarketModel:
    """순부하 기반 제주 가격 생성기.

    파라미터는 제주 계통의 알려진 특징을 반영한 값이다.
    실측 데이터가 들어오면 calibrate()로 덮어쓴다.
    """

    peak_demand_mw: float = 1000.0      # 제주 최대수요 규모 (정규화 기준)
    solar_cap_mw: float = 600.0         # 태양광 설비
    wind_cap_mw: float = 400.0          # 풍력 설비
    must_run_mw: float = 350.0          # 경직성 전원 최소출력 (내연·연계선)
    base_price: float = 95.0            # 순부하가 기준일 때의 가격 ₩/kWh
    price_gamma: float = 2.2            # 순부하 민감도 (클수록 가파름)
    price_cap: float = 300.0
    curtail_price: float = 0.0          # 출력제어 시 가격 (제도상 하한)
    da_forecast_err: float = 0.18       # 재생 하루전 예측오차 (제주는 크다)
    # ── 캘리브레이션 ──────────────────────────────────────────
    # target_mean : 연평균 가격 수준을 실측(KPX 제주 월별 SMP)에 맞춘다.
    # spread_scale: 일중 변동폭 배율. **이것이 이 모델의 가장 중요한 가정이다.**
    #   1.0 = 모델 원본(육지 실측 스프레드의 약 2.4배)
    #   0.41 ≈ 육지 실측과 동일한 스프레드
    #   제주 RT가 육지 DA보다 변동이 크다는 것은 방향적으로 타당하지만,
    #   '얼마나' 큰지는 실측 없이는 알 수 없다. 그래서 값을 노출하고
    #   breakeven_spread()로 손익분기 배율을 함께 보고한다.
    target_mean: float | None = 66.0    # KPX 최근 12개월 제주 ≈ 육지 수준
    spread_scale: float = 1.0

    def _shape(self, price: np.ndarray) -> np.ndarray:
        """일중 변동폭을 조정하고, 전체 수준을 실측 평균에 맞춘다.

        변동폭은 그날 평균을 축으로 압축/확대하고(=계절성 보존),
        수준 보정은 **연 단위로 한 번 구한 상수**를 곱한다.
        일별로 평균을 맞추면 계절 가격차가 사라져 버린다.
        """
        if self.spread_scale != 1.0:
            mu = float(price.mean())
            price = mu + (price - mu) * self.spread_scale
        return np.clip(price * self._level_factor(), 0.0, self.price_cap)

    def _level_factor(self) -> float:
        """수준 보정 상수 — 최초 1회 샘플링해 캐시."""
        if self.target_mean is None:
            return 1.0
        if getattr(self, "_lvl", None) is None:
            rng = random.Random(0)
            vals = []
            for d in range(0, 365, 7):
                dem, sol, wnd = self.demand(d + 1), self.solar(d + 1, rng), self.wind(d + 1, rng)
                raw, _ = self._raw_price(dem - sol - wnd)
                vals.append(float(raw.mean()))
            base = sum(vals) / max(len(vals), 1)
            self._lvl = self.target_mean / base if base > 1e-6 else 1.0
        return float(self._lvl)

    def demand(self, doy: int) -> np.ndarray:
        """15분 단위 수요 곡선 (계절 + 일중 패턴)."""
        t = np.arange(SLOTS) * SLOT_H
        # 일중: 새벽 저점, 오전·저녁 쌍봉
        shape = (0.72 + 0.16 * np.sin((t - 8) / 24 * 2 * math.pi)
                 + 0.14 * np.exp(-((t - 20) ** 2) / 6)
                 + 0.08 * np.exp(-((t - 11) ** 2) / 8))
        # 계절: 여름·겨울 높고 봄·가을 낮다
        seas = 1.0 + 0.14 * math.cos((doy - 15) / 365 * 2 * math.pi) \
                   + 0.10 * math.cos((doy - 200) / 365 * 2 * math.pi)
        return np.clip(shape * seas, 0.35, 1.15) * self.peak_demand_mw

    def solar(self, doy: int, rng: random.Random) -> np.ndarray:
        """태양광 출력 — 정오 집중, 구름에 따른 일간 변동."""
        t = np.arange(SLOTS) * SLOT_H
        clear = np.clip(np.sin((t - 6.5) / 11.5 * math.pi), 0, None) ** 1.3
        seas = 0.78 + 0.22 * math.cos((doy - 172) / 365 * 2 * math.pi)   # 하지 최대
        cloud = max(0.15, rng.gauss(0.82, 0.22))
        return clear * seas * cloud * self.solar_cap_mw

    def wind(self, doy: int, rng: random.Random) -> np.ndarray:
        """풍력 출력 — 겨울에 강하고, 시간적으로 뭉쳐서 변한다(AR(1))."""
        seas = 0.55 + 0.35 * math.cos((doy - 15) / 365 * 2 * math.pi)
        lvl = np.clip(rng.gauss(seas, 0.25), 0.02, 1.0)
        out, e = [], 0.0
        for _ in range(SLOTS):
            e = 0.92 * e + 0.39 * rng.gauss(0, 0.12)     # 자기상관 잡음
            out.append(np.clip(lvl + e, 0.0, 1.0))
        return np.asarray(out) * self.wind_cap_mw

    def _raw_price(self, net: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """캘리브레이션 전 원가격 — 순부하에 볼록하게 반응."""
        curtail = net < self.must_run_mw
        ref = self.peak_demand_mw * 0.62                  # 가격 기준점이 되는 순부하
        ratio = np.clip(net / ref, 0.05, 2.2)
        price = np.clip(self.base_price * ratio ** self.price_gamma, 0.0, self.price_cap)
        return price, curtail

    def price_from_net(self, net: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """순부하 → 실시간 가격 + 출력제어 여부.

        핵심 비선형성: 순부하가 최소출력 아래면 공급 과잉 → 출력제어 → 가격 0.
        그 위에서는 여유가 줄수록 가파르게 오른다 (볼록).
        캘리브레이션(수준·변동폭)은 출력제어 0원 처리 **전에** 적용한다.
        """
        price, curtail = self._raw_price(net)
        price = self._shape(price)
        price[curtail] = self.curtail_price
        return price, curtail

    def day(self, doy: int, rng: random.Random) -> JejuDay:
        """하루치 시장 상태 — 실현(RT)과 하루전 예측(DA)을 함께 만든다."""
        dem = self.demand(doy)
        sol = self.solar(doy, rng)
        wnd = self.wind(doy, rng)
        net = dem - sol - wnd
        rt, curtail = self.price_from_net(net)

        # 하루전 예측: 재생 출력을 틀리게 본다 → 순부하·가격이 어긋난다
        bias = rng.gauss(0.0, self.da_forecast_err)
        e = 0.0
        sol_f, wnd_f = [], []
        for i in range(SLOTS):
            e = 0.85 * e + 0.53 * rng.gauss(0, self.da_forecast_err)
            k = 1 + e + bias
            sol_f.append(max(0.0, sol[i] * k))
            wnd_f.append(max(0.0, wnd[i] * k))
        net_f = dem - np.asarray(sol_f) - np.asarray(wnd_f)
        da_slot, _ = self.price_from_net(net_f)
        # 하루전시장은 1시간 단위 → 4슬롯 평균
        da_hour = da_slot.reshape(24, 4).mean(axis=1)

        return JejuDay(doy=doy, net_load=net, net_load_fc=net_f,
                       rt=rt, da_hour=da_hour, curtail=curtail,
                       solar=sol, wind=wnd, demand=dem)

    def calibrate(self, observed_rt: np.ndarray) -> dict:
        """실측 제주 가격이 확보되면 수준·변동성을 맞춘다."""
        if observed_rt.size == 0:
            return {}
        model = self.price_from_net(self.demand(180) * 0.7)[0]
        scale = float(np.mean(observed_rt) / max(np.mean(model), 1e-9))
        self.base_price *= scale
        return {"scale": round(scale, 4), "new_base_price": round(self.base_price, 2)}


@dataclass
class JejuDay:
    doy: int
    net_load: np.ndarray        # 실현 순부하 (96)
    net_load_fc: np.ndarray     # 하루전 예측 순부하 (96)
    rt: np.ndarray              # 실시간 가격 (96)
    da_hour: np.ndarray         # 하루전 가격 (24)
    curtail: np.ndarray         # 출력제어 여부 (96, bool)
    solar: np.ndarray
    wind: np.ndarray
    demand: np.ndarray

    @property
    def da_slot(self) -> np.ndarray:
        return np.repeat(self.da_hour, 4)

    @property
    def curtail_slots(self) -> int:
        return int(self.curtail.sum())


# ══════════════════════════════════════════════════════════════
#  운영 계획 (충·방전 스케줄)
# ══════════════════════════════════════════════════════════════

@dataclass
class Plan:
    """슬롯별 충·방전 계획 (kW, 양수=방전 / 음수=충전)."""
    power: np.ndarray = field(default_factory=lambda: np.zeros(SLOTS))


@dataclass
class Asset:
    """배터리 자산.

    ── behind_meter 가 이 사업의 핵심 분기다 ─────────────────────

    배터리가 **계량기 어느 쪽에 있느냐**로 충전 원가가 완전히 달라진다.
    이걸 구분하지 않으면 아파트 배터리도 시장가로 충전하는 것처럼 계산되어
    제주 출력제어 흡수의 이익을 잘못 귀속시키게 된다.

        behind_meter=True  (계량기 안쪽 · 아파트 전기실)
            한전에서 **소매 요금**으로 산다. 도매 시장가가 0원이 되어도
            아파트는 경부하 요금을 낸다. → 출력제어의 공짜 전력에 접근 불가.

        behind_meter=False (계량기 바깥쪽 · 발전소 연계점)
            시장 참여자다. 자기 발전소에서 나온, 출력제어당할 전력을
            **실질 0원**에 받는다. → 여기서만 흡수 사업이 성립한다.
    """

    power_kw: float = 225.0
    capacity_kwh: float = 180.0
    soc_min: float = 0.15
    soc_max: float = 0.95
    soc_start: float = 0.30
    eff_charge: float = 0.95
    eff_discharge: float = 0.95
    degradation_won: float = 50.0    # 방전 kWh당 열화비용
    # 자산 위치
    behind_meter: bool = False
    # 계시별(TOU) 요금 — 계량기 안쪽 자산은 시장가가 아니라 이 요금표로 거래한다.
    # 경부하 / 중간부하 / 최대부하 3단. 실제 요금표는 계절·계약종별로 다르므로
    # **근사값**이며, 실증 단지 고지서로 교체해야 한다.
    tou_off_won: float = 70.0        # 경부하 (심야)
    tou_mid_won: float = 110.0       # 중간부하
    tou_peak_won: float = 180.0      # 최대부하

    def tou_price(self, slot: int) -> float:
        """15분 슬롯 → 계시별 요금 (₩/kWh)."""
        h = (slot * 15) // 60
        if h < 9 or h >= 23:
            return self.tou_off_won          # 23~09시 경부하
        if 10 <= h < 12 or 13 <= h < 17 or 17 <= h < 19:
            return self.tou_peak_won         # 오전·오후 피크
        return self.tou_mid_won

    @property
    def round_trip(self) -> float:
        return self.eff_charge * self.eff_discharge

    @property
    def site_label(self) -> str:
        return "계량기 안 (아파트)" if self.behind_meter else "계량기 밖 (발전연계)"

    def charge_price(self, market_price: float, slot: int = 0) -> float:
        """이 자산이 실제로 지불하는 충전 단가."""
        return self.tou_price(slot) if self.behind_meter else market_price

    def sell_price(self, market_price: float, slot: int = 0) -> float:
        """이 자산이 방전으로 얻는 단가.

        계량기 안쪽은 시장에 파는 게 아니라 **비싼 소매 전기를 안 사는 것**이므로
        그 시각의 계시별 요금이 곧 회피 단가(=수익)다.
        """
        return self.tou_price(slot) if self.behind_meter else market_price


def simulate(plan: Plan, day: JejuDay, asset: Asset) -> dict:
    """계획을 실제 가격에 태워 손익을 계산한다.

    회계 원칙 — **충전비용을 반드시 뺀다.**
        방전 매출  = 방전kWh × 판매단가
        충전 비용  = 충전kWh × 충전단가
        열화 비용  = 방전kWh × 열화단가

    단가는 자산 위치에 따라 달라진다 (Asset.charge_price / sell_price).
    계량기 안쪽 자산은 출력제어 구간이어도 소매 요금을 내므로 '공짜'가 아니다.
    """
    soc = asset.soc_start * asset.capacity_kwh
    lo, hi = asset.soc_min * asset.capacity_kwh, asset.soc_max * asset.capacity_kwh
    revenue = charge_cost = degradation = 0.0
    dis_kwh = chg_kwh = 0.0
    free_kwh = 0.0                       # 출력제어 구간에서 받은 공짜 전력

    for i in range(SLOTS):
        p = float(plan.power[i])
        p = max(-asset.power_kw, min(asset.power_kw, p))
        mkt = float(day.rt[i])
        if p > 0:                                        # 방전
            out = min(p * SLOT_H, max(0.0, soc - lo) * asset.eff_discharge)
            soc -= out / asset.eff_discharge
            revenue += out * asset.sell_price(mkt, i)
            degradation += out * asset.degradation_won
            dis_kwh += out
        elif p < 0:                                      # 충전
            room = max(0.0, hi - soc)
            take = min(-p * SLOT_H, room / asset.eff_charge)
            soc += take * asset.eff_charge
            unit = asset.charge_price(mkt, i)
            charge_cost += take * unit
            chg_kwh += take
            # '공짜 전력'은 실제로 0원에 받은 경우만 인정한다.
            # 계량기 안쪽 자산은 출력제어 시각이어도 소매요금을 내므로 해당 없음.
            if day.curtail[i] and unit <= 1e-6:
                free_kwh += take

    pnl = revenue - charge_cost - degradation
    return {
        "pnl": round(pnl, 1),
        "revenue": round(revenue, 1),
        "charge_cost": round(charge_cost, 1),
        "degradation": round(degradation, 1),
        "discharge_kwh": round(dis_kwh, 1),
        "charge_kwh": round(chg_kwh, 1),
        "free_kwh": round(free_kwh, 1),
        "free_share": round(free_kwh / chg_kwh, 3) if chg_kwh > 0 else 0.0,
        "margin_per_kwh": round(pnl / dis_kwh, 1) if dis_kwh > 0 else None,
        "end_soc": round(soc / asset.capacity_kwh, 3),
        "curtail_slots": day.curtail_slots,
    }


# ══════════════════════════════════════════════════════════════
#  전략
# ══════════════════════════════════════════════════════════════

def _fill(plan: Plan, idx: list[int], kw: float, budget_kwh: float) -> float:
    """슬롯 목록에 예산이 다할 때까지 출력을 채운다. 남은 예산 반환.

    kw 부호가 방향을 정한다: 양수=방전, 음수=충전.
    """
    for i in idx:
        if budget_kwh <= 0:
            break
        take = min(abs(kw), budget_kwh / SLOT_H)
        plan.power[i] = math.copysign(take, kw)
        budget_kwh -= take * SLOT_H
    return budget_kwh


class NaiveArb:
    """기준선 — 하루전 예측가만 보고 싼 슬롯 충전 / 비싼 슬롯 방전.

    육지에서 하던 그대로다. 제주에서 이게 왜 부족한지 보여주는 대조군.
    """

    name = "naive_arb"
    label = "단순 차익거래 (기준선)"
    description = "DA 예측가 하위 슬롯 충전 · 상위 슬롯 방전"

    def plan(self, day: JejuDay, asset: Asset) -> Plan:
        p = Plan()
        fc = day.da_slot
        usable = (asset.soc_max - asset.soc_start) * asset.capacity_kwh
        out_kwh = (asset.soc_max - asset.soc_min) * asset.capacity_kwh
        order = np.argsort(fc)
        _fill(p, [int(i) for i in order[:16]], -asset.power_kw, usable)
        _fill(p, [int(i) for i in order[::-1][:16]], asset.power_kw, out_kwh)
        return p


class CurtailAbsorb:
    """출력제어 흡수 — 제주 전용 알파.

    '싼 슬롯'이 아니라 **'버려지는 슬롯'**을 노린다. 둘은 다르다:
    싼 슬롯은 여전히 40원을 내야 하지만, 출력제어 슬롯은 0원이다.

    예측 신호는 가격이 아니라 **순부하**다.
    순부하가 최소출력 아래로 내려갈 것으로 보이는 슬롯 = 출력제어 예상 슬롯.
    가격 예측보다 순부하 예측이 쉽다 — 기상예보로 상당 부분 설명되기 때문이다.
    """

    name = "curtail_absorb"
    label = "출력제어 흡수"
    description = "순부하 예측 하위(=출력제어 예상) 슬롯 집중 충전 · 순부하 최고 슬롯 방전"

    def __init__(self, must_run_mw: float = 350.0, margin: float = 1.10) -> None:
        self.must_run_mw, self.margin = must_run_mw, margin

    def plan(self, day: JejuDay, asset: Asset) -> Plan:
        p = Plan()
        nf = day.net_load_fc
        usable = (asset.soc_max - asset.soc_start) * asset.capacity_kwh
        out_kwh = (asset.soc_max - asset.soc_min) * asset.capacity_kwh

        # 1) 출력제어가 예상되는 슬롯 (여유를 둬서 조금 넓게 잡는다)
        risk = [int(i) for i in np.argsort(nf) if nf[int(i)] < self.must_run_mw * self.margin]
        left = _fill(p, risk, -asset.power_kw, usable)
        # 2) 예상 슬롯이 부족하면 나머지는 순부하 최저 슬롯으로 보충
        if left > 0:
            rest = [int(i) for i in np.argsort(nf) if p.power[int(i)] == 0]
            left = _fill(p, rest[:20], -asset.power_kw, left)

        # 3) 방전은 순부하가 가장 빡빡한 슬롯 (= 가격이 가장 높을 슬롯)
        tight = [int(i) for i in np.argsort(-nf) if p.power[int(i)] == 0]
        _fill(p, tight[:24], asset.power_kw, out_kwh)
        return p


class RampRider:
    """램프 대응 — 순부하가 가장 가파르게 오르는 구간에 방전을 몰아준다.

    제주는 태양광 비중이 높아 일몰 직후 순부하가 급등한다(덕커브 램프).
    이 구간은 가격뿐 아니라 **계통 스트레스**가 가장 큰 시간이고,
    배터리가 가장 필요한 시간이기도 하다. 즉 돈과 명분이 일치한다.
    """

    name = "ramp_rider"
    label = "램프 대응 (덕커브)"
    description = "순부하 상승률 최대 구간 방전 · 태양광 정점 구간 충전"

    def plan(self, day: JejuDay, asset: Asset) -> Plan:
        p = Plan()
        nf = day.net_load_fc
        ramp = np.gradient(nf)
        usable = (asset.soc_max - asset.soc_start) * asset.capacity_kwh
        out_kwh = (asset.soc_max - asset.soc_min) * asset.capacity_kwh

        # 하강 램프(태양광이 올라오는 구간)에 충전
        down = [int(i) for i in np.argsort(ramp)]
        _fill(p, down[:20], -asset.power_kw, usable)
        # 상승 램프(일몰) 구간에 방전
        up = [int(i) for i in np.argsort(-ramp) if p.power[int(i)] == 0]
        _fill(p, up[:20], asset.power_kw, out_kwh)
        return p


class BasisAware:
    """DA-RT 베이시스 인지 — 예측이 빗나갈 방향을 이용한다.

    제주는 재생 예측오차가 커서 DA와 RT가 크게 벌어진다.
    재생이 예보보다 많이 나오면 RT가 DA보다 싸지고(공급 과잉),
    적게 나오면 RT가 비싸진다.

    우리는 **재생 비중이 높은 슬롯일수록 RT가 더 흔들린다**는 성질을 쓴다:
      - 재생 비중 높은 슬롯 → RT가 아래로 튈 가능성 큼 → 충전 기회
      - 재생 비중 낮은 슬롯 → RT가 위로 튈 가능성 큼 → 방전 기회
    변동성 자체를 수익원으로 삼는 것이므로, 방향을 못 맞춰도 손실이 제한된다.
    """

    name = "basis_aware"
    label = "DA-RT 베이시스"
    description = "재생 비중이 높은 슬롯 충전 · 낮은 슬롯 방전 (예측오차 노출 활용)"

    def plan(self, day: JejuDay, asset: Asset) -> Plan:
        p = Plan()
        # 재생 비중 = (태양광+풍력) / 수요. 높을수록 하방 리스크가 크다
        share = (day.solar + day.wind) / np.maximum(day.demand, 1.0)
        usable = (asset.soc_max - asset.soc_start) * asset.capacity_kwh
        out_kwh = (asset.soc_max - asset.soc_min) * asset.capacity_kwh
        hi = [int(i) for i in np.argsort(-share)]
        _fill(p, hi[:20], -asset.power_kw, usable)
        lo = [int(i) for i in np.argsort(share) if p.power[int(i)] == 0]
        _fill(p, lo[:20], asset.power_kw, out_kwh)
        return p


class HybridJeju:
    """운영 전략 — 출력제어 흡수로 연료를 확보하고, 램프에 판다.

    충전은 CurtailAbsorb(연료비 최소화), 방전은 RampRider(매출 최대화).
    제주에서 배터리가 하는 일을 그대로 옮긴 형태다.
    """

    name = "hybrid_jeju"
    label = "제주 하이브리드 (운영안)"
    description = "출력제어 슬롯 충전 + 램프 구간 방전 + 변동비 하한 적용"

    def __init__(self, must_run_mw: float = 350.0) -> None:
        self.absorb = CurtailAbsorb(must_run_mw)

    def plan(self, day: JejuDay, asset: Asset) -> Plan:
        p = Plan()
        nf = day.net_load_fc
        usable = (asset.soc_max - asset.soc_start) * asset.capacity_kwh
        out_kwh = (asset.soc_max - asset.soc_min) * asset.capacity_kwh

        # 충전: 출력제어 예상 슬롯 우선
        risk = [int(i) for i in np.argsort(nf) if nf[int(i)] < self.absorb.must_run_mw * 1.10]
        left = _fill(p, risk, -asset.power_kw, usable)
        if left > 0:
            rest = [int(i) for i in np.argsort(nf) if p.power[int(i)] == 0]
            left = _fill(p, rest[:20], -asset.power_kw, left)

        # 방전: 램프 + 순부하 수준을 함께 본다
        ramp = np.gradient(nf)
        score = 0.6 * (nf / max(nf.max(), 1.0)) + 0.4 * (ramp / max(abs(ramp).max(), 1e-9))
        order = [int(i) for i in np.argsort(-score) if p.power[int(i)] == 0]

        # 변동비 하한: 예상 충전단가로 계산한 변동비를 밑도는 슬롯에는 팔지 않는다
        chg_slots = [i for i in range(SLOTS) if p.power[i] < 0]
        exp_charge = float(np.mean([day.da_slot[i] for i in chg_slots])) if chg_slots else 0.0
        floor = exp_charge / max(0.05, asset.round_trip) + asset.degradation_won
        order = [i for i in order if day.da_slot[i] >= floor]

        _fill(p, order[:24], asset.power_kw, out_kwh)
        return p


# ══════════════════════════════════════════════════════════════
#  실시간(RT) 알고리즘 매매 — 롤링 예측 + 재계획
# ══════════════════════════════════════════════════════════════
#
#  하루전 계획만 세우는 전략들과 근본적으로 다른 점:
#
#    DA 전략 : 아침에 하루치 계획을 짜고 그대로 실행한다.
#              예측이 틀려도 고칠 수 없다.
#    RT 전략 : 15분마다 지금까지 관측한 값으로 예측을 갱신하고,
#              남은 시간에 대해 계획을 다시 짠다.
#
#  **실시간시장의 가치는 가격이 더 좋아서가 아니라, 틀렸을 때 고칠 수 있다는 데 있다.**
#  제주처럼 재생 예측오차가 큰 계통에서는 이 차이가 그대로 손익이 된다.


def _apply(kw: float, soc: float, basis: float, lo: float, hi: float,
           asset: "Asset", charge_unit: float) -> tuple[float, float]:
    """슬롯 실행 후 SOC와 평균 매입단가를 갱신한다.

    매입단가는 가중평균으로 굴린다 (충전하면 섞이고, 방전해도 단가는 그대로).
    simulate()와 같은 물리 규칙을 써야 계획과 실행이 어긋나지 않는다.
    """
    if kw > 0:                                   # 방전
        out = min(kw * SLOT_H, max(0.0, soc - lo) * asset.eff_discharge)
        soc -= out / asset.eff_discharge
    elif kw < 0:                                 # 충전
        take = min(-kw * SLOT_H, max(0.0, hi - soc) / asset.eff_charge)
        added = take * asset.eff_charge
        if soc + added > 1e-9:
            basis = (basis * soc + charge_unit * added) / (soc + added)
        soc += added
    return soc, basis


@dataclass
class SlotState:
    """현재 슬롯에서 컨트롤러가 볼 수 있는 정보 (미래 실현값은 없다)."""
    slot: int                    # 지금 몇 번째 15분 슬롯인가 (0~95)
    soc_kwh: float               # 현재 저장 에너지
    price_now: float             # 지금 슬롯 가격 (관측됨)
    net_now: float               # 지금 순부하 (관측됨)
    curtail_now: bool            # 지금 출력제어 중인가
    net_fc: np.ndarray           # 남은 슬롯 순부하 예측 (길이 SLOTS, 과거는 실측)
    price_fc: np.ndarray         # 남은 슬롯 가격 예측
    cost_basis: float = 0.0      # 지금 배터리에 담긴 전기의 평균 매입단가 (₩/kWh)


class NetLoadForecaster:
    """순부하 롤링 예측기.

    핵심 성질 하나만 지킨다: **가까운 미래일수록 정확하다.**
        15분 뒤  → 거의 맞음 (관성)
        6시간 뒤 → 하루전 예보 수준

    수식은 단순하다. 하루전 예보를 기준으로 두고,
    현재 시점의 실측 오차(bias)를 관측해 가까운 구간부터 보정해 나간다.
    실무의 nowcasting(초단기 예보)과 같은 발상이다.

        예측(h) = 하루전예보(h) + 현재관측오차 × exp(-h / τ)

    τ 가 작을수록 '지금 틀린 만큼'이 빨리 잊힌다.
    """

    def __init__(self, tau_slots: float = 10.0) -> None:
        self.tau = tau_slots

    def forecast(self, day: JejuDay, slot: int) -> np.ndarray:
        """slot 시점에서 본 전체 순부하 곡선 (과거는 실측, 미래는 예측)."""
        out = day.net_load_fc.copy()
        out[: slot + 1] = day.net_load[: slot + 1]          # 지난 구간은 이미 관측됨

        # 최근 관측에서 드러난 예보 오차 (최근 4슬롯=1시간 평균)
        lo = max(0, slot - 3)
        err = float(np.mean(day.net_load[lo: slot + 1] - day.net_load_fc[lo: slot + 1]))

        for h in range(1, SLOTS - slot):
            decay = math.exp(-h / self.tau)
            out[slot + h] = day.net_load_fc[slot + h] + err * decay
        return out


class RollingRT:
    """실시간 알고리즘 매매 — 매 슬롯 재계획(receding horizon).

    매 15분마다 다음을 반복한다:
      1. 지금까지의 실측으로 남은 구간 순부하를 다시 예측한다
      2. 예측 순부하 → 예상 가격, 그리고 출력제어 예상 슬롯을 다시 식별한다
      3. **지금 이 슬롯에 대해서만** 충전/방전/대기를 결정한다
      4. 다음 슬롯에서 1번부터 다시

    의사결정 규칙 (변동비 기반):
      - 지금이 출력제어(또는 예상 변동비 이하) → 충전. 연료가 공짜에 가깝다
      - 지금 가격이 '남은 구간에서 팔 수 있는 값 − 열화비용'보다 높음 → 방전
      - 둘 다 아니면 대기. **안 하는 것도 결정이다**

    기회비용을 명시적으로 쓰는 게 핵심이다. 지금 파는 것은
    '나중에 더 비싸게 팔 기회'를 버리는 일이므로, 남은 구간 상위 분위수와 비교한다.
    """

    name = "rolling_rt"
    label = "실시간 롤링 (RT 재계획)"
    description = "15분마다 순부하 재예측 → 변동비·기회비용 비교 후 충·방전 결정"

    def __init__(self, model: JejuMarketModel | None = None,
                 sell_quantile: float = 0.80, buy_quantile: float = 0.20,
                 tau_slots: float = 10.0) -> None:
        self.model = model or JejuMarketModel()
        self.fc = NetLoadForecaster(tau_slots)
        self.sell_q, self.buy_q = sell_quantile, buy_quantile

    def decide(self, st: SlotState, asset: Asset) -> float:
        """이번 슬롯 출력 (kW, 양수=방전 / 음수=충전)."""
        lo = asset.soc_min * asset.capacity_kwh
        hi = asset.soc_max * asset.capacity_kwh
        future = st.price_fc[st.slot + 1:]
        if future.size == 0:
            future = np.asarray([st.price_now])

        charge_unit = asset.charge_price(st.price_now, st.slot)
        sell_unit = asset.sell_price(st.price_now, st.slot)

        # ── 변동비는 '지금 가격'이 아니라 '담긴 전기의 매입원가'로 따진다 ──
        # 트레이딩의 평균매입단가(cost basis)와 같은 개념이다.
        # 지금 가격으로 계산하면 판매가 < 판매가/효율 + 열화 가 되어
        # 방전 조건이 영원히 성립하지 않는다 (실제로 그 버그가 있었다).
        sell_var_cost = st.cost_basis / max(0.05, asset.eff_discharge) + asset.degradation_won
        # 신규 매입 판단에는 지금 가격 기준 변동비를 쓴다
        buy_var_cost = charge_unit / max(0.05, asset.round_trip) + asset.degradation_won
        # 남은 구간에 기대할 수 있는 판매가 / 매입가 (기회비용의 기준).
        # 계량기 안쪽 자산은 단가가 요금제로 고정이라 분위수를 볼 필요가 없다.
        if asset.behind_meter:
            # 남은 시간의 계시별 요금 분포로 기회비용을 잡는다.
            # (시장가가 아니라 요금표가 이 자산의 '가격'이다)
            tou = np.asarray([asset.tou_price(j) for j in range(st.slot + 1, SLOTS)]) \
                if st.slot + 1 < SLOTS else np.asarray([asset.tou_price(st.slot)])
            sell_ref = float(np.quantile(tou, self.sell_q))
            buy_ref = float(np.quantile(tou, self.buy_q))
        else:
            sell_ref = float(np.quantile(future, self.sell_q))
            buy_ref = float(np.quantile(future, self.buy_q))

        room = hi - st.soc_kwh
        usable = st.soc_kwh - lo

        # ── 충전 판단 ──
        # 지금 사는 게 남은 구간에서 살 수 있는 값보다 싸고,
        # 그렇게 산 전기를 나중에 팔았을 때 남는다면 충전한다.
        if room > 0.1 and charge_unit <= buy_ref + 1e-6:
            if sell_ref - buy_var_cost > 0 or st.curtail_now:
                return -min(asset.power_kw, room / SLOT_H / asset.eff_charge)

        # ── 방전 판단 ──
        # 지금 팔아서 매입원가+열화를 넘고, 남은 구간 기대가보다도 좋으면 판다.
        if usable > 0.1 and sell_unit >= sell_var_cost and sell_unit >= sell_ref:
            return min(asset.power_kw, usable * asset.eff_discharge / SLOT_H)

        return 0.0     # 대기

    def run(self, day: JejuDay, asset: Asset) -> Plan:
        """하루를 슬롯 단위로 진행하며 계획을 만들어 간다."""
        p = Plan()
        soc = asset.soc_start * asset.capacity_kwh
        lo = asset.soc_min * asset.capacity_kwh
        hi = asset.soc_max * asset.capacity_kwh

        basis = 0.0                      # 담긴 전기의 평균 매입단가

        for i in range(SLOTS):
            net_fc = self.fc.forecast(day, i)
            price_fc, _ = self.model.price_from_net(net_fc)
            st = SlotState(
                slot=i, soc_kwh=soc, price_now=float(day.rt[i]),
                net_now=float(day.net_load[i]), curtail_now=bool(day.curtail[i]),
                net_fc=net_fc, price_fc=price_fc, cost_basis=basis,
            )
            kw = self.decide(st, asset)
            p.power[i] = kw
            soc, basis = _apply(kw, soc, basis, lo, hi, asset,
                                asset.charge_price(float(day.rt[i]), i))
        return p

    # 정적 전략과 같은 인터페이스로 노출
    def plan(self, day: JejuDay, asset: Asset) -> Plan:
        return self.run(day, asset)


class DayAheadOnly(RollingRT):
    """대조군 — 같은 규칙을 쓰되 **하루전 예보만** 보고 재계획하지 않는다.

    RollingRT와의 차이는 정보 갱신 여부 하나뿐이다.
    두 전략의 손익 차이가 곧 **'실시간으로 반응할 수 있는 능력'의 값**이다.
    """

    name = "day_ahead_only"
    label = "하루전 고정 (대조군)"
    description = "같은 규칙, 재계획 없음 — 실시간 반응의 가치를 분리 측정"

    def run(self, day: JejuDay, asset: Asset) -> Plan:
        p = Plan()
        soc = asset.soc_start * asset.capacity_kwh
        lo = asset.soc_min * asset.capacity_kwh
        hi = asset.soc_max * asset.capacity_kwh
        # 하루전 예보 곡선을 하루 내내 그대로 쓴다 (갱신 없음)
        net_fc = day.net_load_fc.copy()
        price_fc, curtail_fc = self.model.price_from_net(net_fc)

        basis = 0.0

        for i in range(SLOTS):
            st = SlotState(
                slot=i, soc_kwh=soc,
                price_now=float(price_fc[i]),          # 실현가가 아니라 '예보가'로 판단
                net_now=float(net_fc[i]), curtail_now=bool(curtail_fc[i]),
                net_fc=net_fc, price_fc=price_fc, cost_basis=basis,
            )
            kw = self.decide(st, asset)
            p.power[i] = kw
            soc, basis = _apply(kw, soc, basis, lo, hi, asset,
                                asset.charge_price(float(price_fc[i]), i))
        return p


def jeju_registry() -> dict:
    return {
        "naive_arb": NaiveArb,
        "curtail_absorb": CurtailAbsorb,
        "ramp_rider": RampRider,
        "basis_aware": BasisAware,
        "hybrid_jeju": HybridJeju,
        "day_ahead_only": DayAheadOnly,
        "rolling_rt": RollingRT,
    }


# ══════════════════════════════════════════════════════════════
#  백테스트
# ══════════════════════════════════════════════════════════════

def backtest(strategy, model: JejuMarketModel, asset: Asset,
             days: int = 365, seed: int = 7) -> dict:
    """1년치 제주 RT 시장 백테스트."""
    rng = random.Random(seed)
    rows = []
    for d in range(days):
        day = model.day(d % 365 + 1, rng)
        rows.append(simulate(strategy.plan(day, asset), day, asset))

    p = np.asarray([r["pnl"] for r in rows], dtype=float)
    eq = np.cumsum(p)
    dd = eq - np.maximum.accumulate(eq)
    dis = sum(r["discharge_kwh"] for r in rows)
    chg = sum(r["charge_kwh"] for r in rows)
    free = sum(r["free_kwh"] for r in rows)
    sd = float(p.std(ddof=1)) if len(p) > 1 else 0.0

    return {
        "strategy": getattr(strategy, "name", type(strategy).__name__),
        "label": getattr(strategy, "label", ""),
        "daily_mean_won": round(float(p.mean())),
        "annual_won": round(float(p.sum())),
        "sharpe": round(float(p.mean()) / sd * math.sqrt(365), 2) if sd > 0 else None,
        "max_drawdown_won": round(float(-dd.min())) if len(dd) else 0,
        "hit_rate": round(float((p > 0).mean()), 3),
        "worst_day_won": round(float(p.min())),
        "discharge_kwh": round(dis),
        "charge_kwh": round(chg),
        "free_kwh": round(free),
        "free_share": round(free / chg, 3) if chg > 0 else 0.0,
        "revenue_won": round(sum(r["revenue"] for r in rows)),
        "charge_cost_won": round(sum(r["charge_cost"] for r in rows)),
        "degradation_won": round(sum(r["degradation"] for r in rows)),
        "margin_per_kwh": round(float(p.sum()) / dis, 1) if dis > 0 else None,
        "avg_curtail_slots": round(float(np.mean([r["curtail_slots"] for r in rows])), 1),
        "days": days,
    }


def leaderboard(days: int = 365, seed: int = 7,
                model: JejuMarketModel | None = None,
                asset: Asset | None = None) -> dict:
    """제주 RT 전략 리더보드 — 콘솔·발표용."""
    m = model or JejuMarketModel()
    a = asset or Asset()
    rows = [backtest(cls(), m, a, days, seed) for cls in jeju_registry().values()]
    rows.sort(key=lambda r: -r["annual_won"])
    return {
        "market": "제주 실시간시장 (모델)",
        "disclaimer": (
            "제주 RT 체결가 실측 시계열이 공개되지 않아 순부하 기반 물리 모델로 생성한 결과다. "
            "수준·변동성은 EPSIS 실측 확보 시 calibrate()로 보정한다."
        ),
        "asset": {"power_kw": a.power_kw, "capacity_kwh": a.capacity_kwh,
                  "degradation_won": a.degradation_won, "round_trip": round(a.round_trip, 3)},
        "leaderboard": rows,
    }

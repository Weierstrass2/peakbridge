"""
VPP(가상발전소) 시뮬레이터.

여러 단지의 묶음 ESS를 하나의 포트폴리오로 통합해
가용 유연성(kW), 수요반응(DR) 수익, 차익거래 수익을 계산합니다.
순수 계산 모듈 — 외부 의존성 없음.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# ── 사업 모델 가정 ─────────────────────────────────────
PEAKBRIDGE_FEE_RATE = 0.15   # PeakBridge 수수료 15%
DR_EVENTS_PER_MONTH = 25     # 월 평균 DR 이벤트 횟수 (평일 기준)
DEFAULT_ESS_CAPACITY_KWH = 100.0
DEFAULT_ESS_POWER_KW = 50.0  # 단지당 최대 방전 출력
MIN_SOC_PERCENT = 20.0       # 방전 하한


class VPPSimulator:
    """다중 단지 ESS 통합 관제 계산기."""

    def calculate_portfolio(self, buildings: list[dict]) -> dict:
        """
        여러 단지 ESS 통합 포트폴리오.

        buildings 항목: { building_id, ess_capacity(kWh), current_soc(%),
                          max_power_kw(선택) }
        """
        items = []
        total_capacity = 0.0
        total_flex = 0.0

        for b in buildings or []:
            try:
                capacity = float(b.get("ess_capacity", DEFAULT_ESS_CAPACITY_KWH))
                soc = float(b.get("current_soc", 0.0))
                max_kw = float(b.get("max_power_kw", DEFAULT_ESS_POWER_KW))

                # 방전 가능 에너지 (SOC 하한 위 잔량)
                usable_ratio = max(0.0, (soc - MIN_SOC_PERCENT) / 100.0)
                usable_kwh = capacity * usable_ratio
                # 가용 유연성: 출력 한계와 1시간 방전 기준 에너지 한계 중 작은 값
                available_kw = round(min(max_kw, usable_kwh), 1)

                items.append(
                    {
                        "building_id": b.get("building_id", "unknown"),
                        "ess_capacity": capacity,
                        "current_soc": soc,
                        "usable_kwh": round(usable_kwh, 1),
                        "available_kw": available_kw,
                        "live": bool(b.get("live", False)),
                    }
                )
                total_capacity += capacity
                total_flex += available_kw
            except Exception as exc:
                logger.warning("vpp_building_skipped", building=b, error=str(exc))

        return {
            "total_capacity_kwh": round(total_capacity, 1),
            "available_flexibility_kw": round(total_flex, 1),
            "building_count": len(items),
            "buildings": items,
        }

    def calculate_dr_revenue(
        self,
        reduction_kw: float,
        duration_hours: float,
        smp_price: float,
    ) -> dict:
        """수요반응(DR) 참여 수익 계산."""
        reduction_kw = max(0.0, reduction_kw)
        duration_hours = max(0.0, duration_hours)
        smp_price = max(0.0, smp_price)

        reduction_kwh = reduction_kw * duration_hours
        gross = reduction_kwh * smp_price
        fee = gross * PEAKBRIDGE_FEE_RATE
        net = gross - fee

        return {
            "reduction_kwh": round(reduction_kwh, 1),
            "smp_price": smp_price,
            "gross_revenue": round(gross, 0),
            "peakbridge_fee": round(fee, 0),
            "net_revenue": round(net, 0),
            "monthly_projection": round(net * DR_EVENTS_PER_MONTH, 0),
            "fee_rate": PEAKBRIDGE_FEE_RATE,
        }

    def calculate_arbitrage(
        self,
        charged_kwh: float,
        discharged_kwh: float,
        charge_price: float,
        discharge_price: float,
    ) -> dict:
        """차익거래(싸게 충전 → 비싸게 방전) 수익 계산."""
        charged_kwh = max(0.0, charged_kwh)
        discharged_kwh = max(0.0, discharged_kwh)

        charge_cost = charged_kwh * max(0.0, charge_price)
        discharge_savings = discharged_kwh * max(0.0, discharge_price)
        arbitrage = discharge_savings - charge_cost
        roi = (arbitrage / charge_cost * 100.0) if charge_cost > 0 else 0.0
        efficiency = (discharged_kwh / charged_kwh * 100.0) if charged_kwh > 0 else 0.0

        return {
            "charged_kwh": charged_kwh,
            "discharged_kwh": discharged_kwh,
            "charge_cost": round(charge_cost, 0),
            "discharge_savings": round(discharge_savings, 0),
            "arbitrage": round(arbitrage, 0),
            "roi_percent": round(roi, 1),
            "round_trip_ratio": round(efficiency, 1),
            "monthly_projection": round(arbitrage * 30, 0),
        }


vpp_simulator = VPPSimulator()

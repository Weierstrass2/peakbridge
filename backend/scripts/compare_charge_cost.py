"""충전비용 반영 전후 비교 — 우리 백테스트가 얼마나 과대평가였는지 확인한다.

이전 백테스트는 `매출 − 열화비용`만 계산했다. 즉 **충전 전기를 공짜로 얻은 셈**
치고 있었다. 방전하려면 반드시 먼저 사와야 하므로 이건 회계 누락이다.

실행:
    cd backend
    python scripts/compare_charge_cost.py --days 120
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.resources import MARKET_RULES, ess_resources  # noqa: E402
from app.services import market_data  # noqa: E402
from app.services.strategies import MarketSimulator, registry, run_backtest  # noqa: E402

NAMES = ["topk_safe", "marginal_cost", "greedy_budget", "zscore", "cvar_guard"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    args = ap.parse_args()

    market_data._load_once()
    res = ess_resources()
    power = sum(r["max_discharge_kw"] for r in res.values())
    energy = sum(max(0.0, 60.0 - r["soc_min"]) / 100 * r["capacity_kwh"] for r in res.values())
    days = sorted({(k[0], k[1], k[2]) for k in market_data._price
                   if k[3] == 12 and k[0] < 2026})[-args.days:]

    def sim(**kw):
        return MarketSimulator(
            price_map=market_data._price, dpct_map=market_data._dpct,
            rules=MARKET_RULES, power_kw=power, energy_kwh=energy,
            degradation_won=50.0, **kw,
        )

    scenarios = [
        ("충전비 미반영 (이전 백테스트 = 과대평가)", sim(charge_price_won=0.0)),
        ("시장 충전 (그날 최저가 구간)", sim()),
        ("경부하 요금 충전 ₩70", sim(charge_price_won=70.0)),
    ]

    reg = registry()
    print(f"포트폴리오 {power:.0f}kW / {energy:.0f}kWh · 검증 {len(days)}일")
    for label, s in scenarios:
        print(f"\n== {label} ==")
        for n in NAMES:
            m = run_backtest(reg[n](), s, days).metrics()
            print(f"  {n:<16}{m['daily_mean_won']:>9,}/일   연 {m['annual_won']:>10,}"
                  f"   마진 {str(m['margin_per_kwh']):>7}/kWh   승률 {m['hit_rate']}")
    print("\n해석: 충전비를 넣는 순간 대부분 전략의 마진이 음수로 뒤집힌다.")
    print("      육지 SMP 차익거래는 현재 가격 수준에서 성립하지 않는다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

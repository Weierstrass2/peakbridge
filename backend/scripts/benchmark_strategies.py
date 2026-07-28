"""전략 벤치마크 러너 — 여러 자동매매 알고리즘을 같은 시장에서 겨루게 한다.

실행:
    cd backend
    python scripts/benchmark_strategies.py                 # 기본 (검증 180일)
    python scripts/benchmark_strategies.py --days 300      # 검증 일수 지정
    python scripts/benchmark_strategies.py --walk-forward  # 워크포워드 3분할 추가

결과:
    표준출력 리더보드 + models/strategy_benchmark.json 저장
    (저장본은 /market/strategies/leaderboard API가 그대로 읽어 서빙한다)
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.resources import MARKET_RULES, ess_resources  # noqa: E402
from app.services import market_data  # noqa: E402
from app.services.strategies import (  # noqa: E402
    MarketSimulator,
    bootstrap_ci,
    registry,
    run_backtest,
    split_walk_forward,
)

# 기본 SOC 60% 가정 — 실운영에서는 실측 SOC가 들어온다
DEFAULT_SOC = 60.0


def build_simulator() -> MarketSimulator:
    market_data._load_once()
    res = ess_resources()
    power = sum(r["max_discharge_kw"] for r in res.values())
    energy = sum(
        max(0.0, DEFAULT_SOC - r["soc_min"]) / 100 * r["capacity_kwh"] for r in res.values()
    )
    return MarketSimulator(
        price_map=market_data._price,
        dpct_map=market_data._dpct,
        rules=MARKET_RULES,
        power_kw=power,
        energy_kwh=energy,
        degradation_won=50.0,
    )


def all_days() -> list[tuple[int, int, int]]:
    return sorted({(k[0], k[1], k[2]) for k in market_data._price if k[3] == 12 and k[0] < 2026})


def fmt(v, width=10, money=False):
    if v is None:
        return "—".rjust(width)
    if money:
        return f"{v:,.0f}".rjust(width)
    return f"{v}".rjust(width)


def main() -> int:
    ap = argparse.ArgumentParser(description="VPP 입찰 전략 벤치마크")
    ap.add_argument("--days", type=int, default=180, help="검증 일수")
    ap.add_argument("--seed", type=int, default=999)
    ap.add_argument("--walk-forward", action="store_true", help="워크포워드 3분할 검증 추가")
    ap.add_argument("--forecast-error", type=float, default=0.10,
                    help="하루 전 예측 오차 표준편차 비율 (0 = 완전예지, 기본 0.10)")
    ap.add_argument("--out", default="models/strategy_benchmark.json")
    args = ap.parse_args()

    sim = build_simulator()
    sim.forecast_error = args.forecast_error
    days_pool = all_days()
    if not days_pool:
        print("가격 데이터를 찾지 못했습니다 (data/ev2gym_prices.csv 확인)")
        return 1

    test_days = sorted(random.Random(args.seed).sample(days_pool, min(args.days, len(days_pool))))
    print(f"시장: {len(days_pool)}일 풀 · 검증 {len(test_days)}일 · "
          f"정격 {sim.power_kw:.0f}kW · 가용에너지 {sim.energy_kwh:.0f}kWh · "
          f"예측오차 σ={sim.forecast_error:.0%}\n")

    rows = []
    for name, factory in registry().items():
        strat = factory()
        res = run_backtest(strat, sim, test_days, seed=args.seed)
        m = res.metrics()
        lo, hi = bootstrap_ci(res.pnl)
        m["ci95_low"] = round(lo)
        m["ci95_high"] = round(hi)
        m["name"] = name
        m["family"] = res.family
        m["description"] = res.description
        rows.append(m)

    rows.sort(key=lambda r: r["daily_mean_won"], reverse=True)

    # ── 리더보드 출력 ──
    head = (f"{'전략':<16}{'계열':<12}{'일평균₩':>11}{'Sharpe':>9}{'MDD₩':>12}"
            f"{'승률':>8}{'이행률':>8}{'위약₩':>12}")
    print(head)
    print("─" * len(head))
    for r in rows:
        print(
            f"{r['name']:<16}{r['family']:<12}"
            f"{fmt(r['daily_mean_won'], 11, money=True)}"
            f"{fmt(r['sharpe'], 9)}"
            f"{fmt(r['max_drawdown_won'], 12, money=True)}"
            f"{fmt(r['hit_rate'], 8)}"
            f"{fmt(r['fill_rate'], 8)}"
            f"{fmt(r['penalty_won'], 12, money=True)}"
        )

    best = rows[0]
    print(f"\n최고 전략: {best['name']} — 일평균 ₩{best['daily_mean_won']:,} "
          f"(95% 신뢰구간 ₩{best['ci95_low']:,} ~ ₩{best['ci95_high']:,})")
    print(f"연환산 ₩{best['annual_won']:,} · Sharpe {best['sharpe']} · "
          f"최악의 날 ₩{best['worst_day_won']:,}")

    payload = {
        "test_days": len(test_days),
        "forecast_error": args.forecast_error,
        "power_kw": sim.power_kw,
        "energy_kwh": sim.energy_kwh,
        "leaderboard": rows,
    }

    # ── 워크포워드 (선택) ──
    if args.walk_forward:
        print("\n워크포워드 검증 (시간순 3분할)")
        folds = split_walk_forward(days_pool, n_folds=3)
        wf: dict[str, list[int]] = {}
        for i, (_train, test) in enumerate(folds):
            sample = sorted(random.Random(args.seed + i).sample(test, min(90, len(test))))
            line = []
            for name, factory in registry().items():
                res = run_backtest(factory(), sim, sample, seed=args.seed + i)
                v = res.metrics()["daily_mean_won"]
                wf.setdefault(name, []).append(v)
                line.append(f"{name} ₩{v:,}")
            print(f"  구간 {i + 1} ({len(sample)}일): " + " · ".join(line[:4]) + " …")
        # 구간별 순위 안정성 = 실전 신뢰도
        print("\n  구간 전체에서 흑자를 유지한 전략:")
        for name, vals in sorted(wf.items(), key=lambda kv: -np.mean(kv[1])):
            mark = "O" if all(v > 0 for v in vals) else "X"
            print(f"    [{mark}] {name:<16} 구간별 일평균 " +
                  " / ".join(f"₩{v:,}" for v in vals))
        payload["walk_forward"] = {k: [int(x) for x in v] for k, v in wf.items()}

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(payload, open(out, "w"), ensure_ascii=False, indent=1)
    print(f"\n저장: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

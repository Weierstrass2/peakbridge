"""손익 분해 · 체결품질(TCA) · 예측 품질 — 데스크 애널리틱스.

트레이딩 데스크에서 "얼마 벌었나"보다 중요한 질문은 **"왜 벌었나"**다.
운이 좋아서인지, 전략이 맞아서인지, 예측이 좋아서인지를 분리하지 못하면
다음 날 같은 판단을 반복할 수 없다.

세 축:
  1. P&L Attribution — 손익을 원인별로 쪼갠다 (가격/물량/위약/열화/용량요금)
  2. TCA             — 체결 품질. 입찰가와 실제 체결가의 차이(슬리피지)를 본다
  3. Forecast Quality— 예측 오차와 그 오차가 손익에 끼친 영향
"""

from __future__ import annotations

import numpy as np


# ────────────────────── 1. 손익 분해 ──────────────────────

def attribute_pnl(bids: list[dict], mcp_actual: list[float], mcp_forecast: list[float],
                  usable_kwh: float, degradation_won: float = 50.0,
                  penalty_factor: float = 1.2, cp_rate: float = 8.0) -> dict:
    """일 손익을 구성요소로 분해한다.

    분해 항목:
      base_revenue   — 예측대로 실현됐다면 벌었을 매출 (기준선)
      price_effect   — 실제 가격이 예측과 달라서 생긴 차이
      volume_effect  — 낙찰량이 계획과 달라서 생긴 차이
      penalty        — 이행 실패 위약금 (음수)
      degradation    — 배터리 열화비용 (음수)
      capacity       — 용량요금 (양수, 낙찰 여부와 무관)

    합계는 실제 순손익과 일치한다 (검증 테스트로 확인).
    """
    energy = usable_kwh
    revenue = penalty = degradation = capacity = 0.0
    planned_revenue = 0.0     # 예측 가격 × 이행 가능 물량
    awarded_kwh = delivered_kwh = bid_kwh = 0.0
    price_effect = 0.0

    for b in sorted(bids, key=lambda x: int(x["hour"])):
        h = int(b["hour"])
        q = float(b.get("qty_kw", 0) or 0)
        p = float(b.get("price", 0) or 0)
        if q <= 0:
            continue
        bid_kwh += q
        capacity += q * cp_rate
        if h >= len(mcp_actual):
            continue
        if p > mcp_actual[h]:
            continue                       # 미낙찰
        awarded_kwh += q
        d = min(q, energy)
        energy -= d
        delivered_kwh += d
        revenue += d * mcp_actual[h]
        fc = mcp_forecast[h] if h < len(mcp_forecast) else mcp_actual[h]
        planned_revenue += d * fc
        price_effect += d * (mcp_actual[h] - fc)   # 가격이 예측과 다른 데서 온 차이
        degradation += d * degradation_won
        short = q - d
        if short > 0.5:
            penalty += short * mcp_actual[h] * penalty_factor

    net = revenue - degradation + capacity - penalty
    return {
        "net_won": round(net),
        "components": {
            "base_revenue": round(planned_revenue),
            "price_effect": round(price_effect),
            "capacity_payment": round(capacity),
            "degradation": -round(degradation),
            "penalty": -round(penalty),
        },
        "volume": {
            "bid_kwh": round(bid_kwh, 1),
            "awarded_kwh": round(awarded_kwh, 1),
            "delivered_kwh": round(delivered_kwh, 1),
            "shortfall_kwh": round(awarded_kwh - delivered_kwh, 1),
            "award_rate": round(awarded_kwh / bid_kwh, 3) if bid_kwh else None,
            "fill_rate": round(delivered_kwh / awarded_kwh, 3) if awarded_kwh else None,
        },
    }


# ────────────────────── 2. 체결품질 (TCA) ──────────────────────

def transaction_cost_analysis(bids: list[dict], mcp_actual: list[float]) -> dict:
    """체결 품질 분석.

    주식 TCA의 슬리피지 개념을 옮겼다. 여기서 슬리피지는
    **입찰가와 실제 청산가의 차이**다. pay-as-clear 시장이므로
    입찰가를 낮게 써도 정산은 MCP로 받는다 → 음의 슬리피지가 곧 안전마진이다.

      - 너무 낮게 쓰면: 무조건 낙찰되지만 이행 리스크가 커진다
      - 너무 높게 쓰면: 낙찰이 안 돼 기회를 놓친다 (miss)
    """
    rows = []
    captured = missed_qty = missed_value = 0.0
    slips = []
    for b in sorted(bids, key=lambda x: int(x["hour"])):
        h = int(b["hour"])
        q = float(b.get("qty_kw", 0) or 0)
        p = float(b.get("price", 0) or 0)
        if q <= 0 or h >= len(mcp_actual):
            continue
        mcp = mcp_actual[h]
        awarded = p <= mcp
        slip = mcp - p                      # 양수 = 안전마진
        if awarded:
            slips.append(slip)
            captured += q * mcp
        else:
            missed_qty += q
            missed_value += q * mcp         # 잡을 수 있었던 매출
        rows.append({
            "hour": h,
            "qty_kw": q,
            "bid_price": round(p, 1),
            "mcp": round(mcp, 1),
            "slippage": round(slip, 1),
            "awarded": awarded,
            "value_won": round(q * mcp) if awarded else 0,
        })

    arr = np.asarray(slips) if slips else np.array([0.0])
    return {
        "avg_slippage": round(float(arr.mean()), 2),
        "median_slippage": round(float(np.median(arr)), 2),
        "min_slippage": round(float(arr.min()), 2),      # 가장 아슬아슬했던 체결
        "captured_won": round(captured),
        "missed_qty_kw": round(missed_qty, 1),
        "missed_value_won": round(missed_value),         # 기회손실
        "hit_ratio": round(len(slips) / len(rows), 3) if rows else None,
        "rows": rows,
    }


# ────────────────────── 3. 예측 품질 ──────────────────────

def forecast_quality(forecasts: list[list[float]], actuals: list[list[float]]) -> dict:
    """예측 오차 지표 + 손익 영향.

      MAPE          — 평균 절대 백분율 오차 (직관적 정확도)
      RMSE          — 큰 오차에 벌점을 더 주는 지표
      bias          — 체계적으로 높게/낮게 보는 경향 (양수 = 과대예측)
      pinball loss  — 분위수 예측 품질. 입찰가 결정에 직결되는 비대칭 손실
      calibration   — 예측 구간별 실제 실현 분포 (신뢰도 곡선용)
    """
    if not forecasts or not actuals:
        return {}
    f = np.asarray(forecasts, dtype=float).ravel()
    a = np.asarray(actuals, dtype=float).ravel()
    n = min(len(f), len(a))
    f, a = f[:n], a[:n]
    err = f - a

    mape = float(np.mean(np.abs(err) / np.maximum(a, 1e-6)) * 100)
    rmse = float(np.sqrt(np.mean(err ** 2)))
    bias = float(np.mean(err))

    # pinball loss (q=0.5 기준). 입찰은 비대칭 손실 구조라 이 지표가 적합하다
    q = 0.5
    pinball = float(np.mean(np.maximum(q * (a - f), (q - 1) * (a - f))))

    # 캘리브레이션: 예측 5분위별 평균 예측 vs 평균 실현
    order = np.argsort(f)
    buckets = np.array_split(order, 5)
    calib = [
        {
            "bucket": i + 1,
            "forecast_mean": round(float(f[b].mean()), 1),
            "actual_mean": round(float(a[b].mean()), 1),
            "gap": round(float(f[b].mean() - a[b].mean()), 1),
        }
        for i, b in enumerate(buckets) if len(b)
    ]

    return {
        "samples": int(n),
        "mape_pct": round(mape, 2),
        "rmse": round(rmse, 2),
        "bias": round(bias, 2),
        "pinball_loss": round(pinball, 2),
        "calibration": calib,
        "verdict": (
            "과대예측 경향 — 응찰가를 높게 잡아 미낙찰 위험" if bias > 3
            else "과소예측 경향 — 낮은 응찰가로 이행 부담" if bias < -3
            else "편향 작음"
        ),
    }


# ────────────────────── 4. 롤링 지표 ──────────────────────

def rolling_metrics(pnl: list[float], window: int = 20) -> dict:
    """롤링 Sharpe·드로다운 — 전략이 '지금도' 작동하는지 본다.

    전체 기간 평균은 이미 무너진 전략도 좋아 보이게 만든다.
    데스크에서는 항상 최근 구간을 따로 본다.
    """
    if len(pnl) < 3:
        return {"points": [], "current_sharpe": None, "current_drawdown": 0}
    p = np.asarray(pnl, dtype=float)
    equity = np.cumsum(p)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak

    points = []
    for i in range(len(p)):
        lo = max(0, i - window + 1)
        w = p[lo: i + 1]
        sd = float(w.std(ddof=1)) if len(w) > 1 else 0.0
        sharpe = float(w.mean() / sd * np.sqrt(365)) if sd > 0 else None
        points.append({
            "i": i,
            "pnl": round(float(p[i])),
            "equity": round(float(equity[i])),
            "drawdown": round(float(dd[i])),
            "sharpe": round(sharpe, 2) if sharpe is not None else None,
        })
    return {
        "points": points,
        "current_sharpe": points[-1]["sharpe"],
        "current_drawdown": points[-1]["drawdown"],
        "max_drawdown": round(float(-dd.min())),
        "equity_won": round(float(equity[-1])),
    }

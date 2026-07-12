"""
시장 가격 데이터 엔진 — 10년치 실데이터 기반 MCP 생성.

구성:
  기준가  = 한전 요금 캘린더 실데이터 (ev2gym_prices.csv, 2016~2026, 계절·공휴일 반영)
  희소성 프리미엄 = KPX 실측 수요 백분위 (kpx_processed.csv) — 수요가 높을수록
                    청산가격이 기준 위로 상승 (실제 SMP 형성 원리)
  MCP(t) = 기준가(t)×1000 × (0.95 + 0.55 × 수요백분위(t)²)

지연 로드 (첫 호출 시 1회), 파일 없으면 None 반환 → market_service가 폴백.
"""

from __future__ import annotations

import csv
import random
from datetime import date
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

_loaded = False
# key: (year, month, day, hour) → base price(원), demand percentile(0~1)
_price: dict[tuple[int, int, int, int], float] = {}
_dpct: dict[tuple[int, int, int, int], float] = {}
_years: list[int] = []


def _load_once() -> bool:
    global _loaded
    if _loaded:
        return bool(_price)
    _loaded = True
    try:
        pf = DATA_DIR / "ev2gym_prices.csv"
        with open(pf) as f:
            r = csv.reader(f)
            next(r)
            for row in r:
                ts = row[0]  # "2016-01-01 00:00"
                if ts[14:16] != "00":
                    continue  # 정시만 (5분 → 시간)
                key = (int(ts[0:4]), int(ts[5:7]), int(ts[8:10]), int(ts[11:13]))
                _price[key] = float(row[1]) * 1000.0

        df = DATA_DIR / "kpx_processed.csv"
        demands: list[tuple[tuple[int, int, int, int], float]] = []
        with open(df) as f:
            r = csv.DictReader(f)
            for row in r:
                ts = row["ds"]  # "2016-01-02 00:00:00"
                key = (int(ts[0:4]), int(ts[5:7]), int(ts[8:10]), int(ts[11:13]))
                try:
                    demands.append((key, float(row["kpx_demand_mwh"])))
                except (ValueError, KeyError):
                    continue
        vals = sorted(d for _, d in demands)
        n = len(vals)
        if n:
            import bisect
            for key, d in demands:
                _dpct[key] = bisect.bisect_left(vals, d) / n

        years = sorted({k[0] for k in _price})
        _years.extend(years)
        logger.info(
            "market_data_loaded",
            price_hours=len(_price),
            demand_hours=len(_dpct),
            years=f"{years[0]}~{years[-1]}" if years else "none",
        )
        return True
    except Exception as exc:
        logger.warning("market_data_load_failed", error=str(exc))
        return False


def mcp_day(delivery: date, jitter: float = 1.0) -> list[float] | None:
    """공급일의 24시간 MCP — 같은 월·일의 과거 실데이터 연도에서 재생."""
    if not _load_once():
        return None
    rng = random.Random(delivery.toordinal())
    candidates = [y for y in _years if (y, delivery.month, delivery.day, 12) in _price]
    if not candidates:
        return None
    year = rng.choice(candidates)

    curve: list[float] = []
    for h in range(24):
        key = (year, delivery.month, delivery.day, h)
        base = _price.get(key)
        if base is None:
            base = 84.5
        pct = _dpct.get(key, 0.5)
        premium = 0.95 + 0.55 * (pct ** 2)
        noise = 1.0 + rng.uniform(-0.03, 0.03) * jitter
        curve.append(round(base * premium * noise, 1))
    return curve


def source_info(delivery: date) -> dict:
    """가격 출처 메타 (프론트 표기용)."""
    if not _load_once():
        return {"engine": "shape-model"}
    rng = random.Random(delivery.toordinal())
    candidates = [y for y in _years if (y, delivery.month, delivery.day, 12) in _price]
    return {
        "engine": "historical",
        "replay_year": rng.choice(candidates) if candidates else None,
        "dataset": f"한전 요금 캘린더 {_years[0]}~{_years[-1]} + KPX 수요 백분위",
    }

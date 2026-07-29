"""제주 실데이터 적재 — 모델의 가정을 실측으로 갈아끼운다.

입력 (backend/data/kpx_raw/):
    제주 풍력 출력제어횟수 및 제어량.csv   전력거래소 · 2021~2024 시간별 제어량
    제주 태양광 출력제어횟수.csv           전력거래소
    plusdr_raw.csv                        제주 플러스 DR 실적 2021~2023
    re_forecast_raw.csv                   제주 신재생 출력 예측치 vs 실적
    powerDemandPerformJeju_YYYY-MM.xlsx    제주 전력수급실적 (시간별 최대전력)

산출 (backend/data/):
    jeju_curtailment.csv    일자·시간별 제어량 (MWh)
    jeju_plusdr.csv         플러스 DR 이벤트별 입찰·낙찰·증대·SMP
    jeju_facts.json         모델 캘리브레이션용 통계 요약

── 이 스크립트가 바로잡는 것 ────────────────────────────────

이전 제주 모델은 **"출력제어 = 전기가 남음 = 가격 0원"**을 전제했다.
실측은 정반대다. 출력제어 시각의 제주 SMP는 평균 173원이다.

한국 시장에서 SMP는 한계 발전기(LNG·중유)의 변동비로 결정된다.
재생에너지가 물리적으로 잘려나가도 가격은 화력 기준으로 유지된다.
**남는 전기를 싸게 살 수 있는 메커니즘이 현행 제도에 없다.**

그래서 정부는 가격 대신 **별도 인센티브**로 수요를 끌어올린다 — 그게 플러스 DR이다.
이 스크립트는 그 시장의 실제 크기와 빈틈을 숫자로 뽑는다.

실행:
    cd backend
    python scripts/ingest_jeju_real.py
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "kpx_raw"
OUT = ROOT / "data"

HOUR_COLS = [f"{h}시" for h in range(1, 25)]


def _read(path: Path) -> list[dict]:
    """CP949/UTF-8 자동 판별 CSV 리더."""
    for enc in ("utf-8-sig", "cp949", "utf-8"):
        try:
            rows = list(csv.DictReader(path.open(encoding=enc)))
            if rows and any(rows[0].values()):
                return rows
        except (UnicodeDecodeError, LookupError):
            continue
    return []


def _num(v) -> float | None:
    s = str(v or "").replace(",", "").replace("%", "").strip()
    return float(s) if re.match(r"^-?\d+(\.\d+)?$", s) else None


# ── 1. 출력제어 ────────────────────────────────────────────

def ingest_curtailment() -> dict:
    """제주 풍력·태양광 출력제어 → 일자·시간별 제어량."""
    recs: list[dict] = []
    for src, kind in [("제주 풍력 출력제어횟수 및 제어량.csv", "wind"),
                      ("제주 태양광 출력제어횟수.csv", "solar")]:
        p = RAW / src
        if not p.exists():
            continue
        for r in _read(p):
            day = str(r.get("일자") or "").strip()
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
                continue
            for i, c in enumerate(HOUR_COLS):
                raw = str(r.get(c) or "").strip()
                mwh = _num(raw)
                # 태양광 파일은 제어량 없이 '출력제어' 문자열만 있다 → 발생만 기록
                hit = mwh is not None and mwh > 0 or raw == "출력제어"
                if not hit:
                    continue
                recs.append({"date": day, "hour": i + 1, "kind": kind,
                             "mwh": round(mwh, 2) if mwh else 0.0})

    if not recs:
        return {}

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "jeju_curtailment.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "hour", "kind", "mwh"])
        w.writeheader()
        w.writerows(sorted(recs, key=lambda r: (r["date"], r["hour"])))

    days = {r["date"] for r in recs}
    years = Counter(r["date"][:4] for r in recs)
    year_days = {y: len({r["date"] for r in recs if r["date"][:4] == y}) for y in years}
    by_hour = Counter(r["hour"] for r in recs)
    by_month = Counter(r["date"][5:7] for r in recs)
    total = sum(r["mwh"] for r in recs)
    span = max(1, len(year_days))

    return {
        "event_days": len(days),
        "years": sorted(year_days),
        "days_per_year": round(len(days) / span, 1),
        "day_share": round(len(days) / (365 * span), 3),
        "total_mwh": round(total),
        "mwh_per_event_day": round(total / max(len(days), 1), 1),
        "by_year_days": year_days,
        "top_hours": [h for h, _ in by_hour.most_common(6)],
        "hour_hist": dict(sorted(by_hour.items())),
        "month_hist": dict(sorted(by_month.items())),
    }


# ── 2. 플러스 DR ───────────────────────────────────────────

def ingest_plusdr() -> dict:
    """제주 플러스 DR 실적 → 이벤트별 정규화 + 시장 통계.

    가장 중요한 두 숫자를 뽑는다.
        낙찰률  — 입찰하면 얼마나 낙찰되는가 (경쟁 강도)
        이행률  — 낙찰받고 실제로 얼마나 이행하는가 (시장의 빈틈)
    """
    p = RAW / "plusdr_raw.csv"
    if not p.exists():
        return {}
    rows = _read(p)
    recs = []
    for r in rows:
        hour = _num(r.get("증대시간"))
        if hour is None:
            continue
        recs.append({
            "year": (r.get("연도") or "").strip(),
            "date": (r.get("증대일") or "").strip(),
            "hour": int(hour),
            "base_curtail_mwh": _num(r.get("기준출력 제어량(MWh)")) or 0.0,
            "bid_mwh": _num(r.get("입찰량(MWh)")) or 0.0,
            "cleared_mwh": _num(r.get("낙찰량(MWh)")) or 0.0,
            "delivered_mwh": _num(r.get("증대량(MWh)")) or 0.0,
            "jeju_smp": _num(r.get("제주SMP")) or 0.0,
            "delivery_pct": _num(r.get("증대 이행률")) or 0.0,
        })
    if not recs:
        return {}

    with (OUT / "jeju_plusdr.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(recs[0].keys()))
        w.writeheader()
        w.writerows(recs)

    bid = sum(r["bid_mwh"] for r in recs)
    cleared = sum(r["cleared_mwh"] for r in recs)
    delivered = sum(r["delivered_mwh"] for r in recs)
    smp = [r["jeju_smp"] for r in recs if r["jeju_smp"] > 0]
    rates = [r["delivery_pct"] for r in recs]
    hours = Counter(r["hour"] for r in recs)
    per_year = defaultdict(lambda: {"bid": 0.0, "cleared": 0.0, "delivered": 0.0, "events": 0})
    for r in recs:
        y = per_year[r["year"]]
        y["bid"] += r["bid_mwh"]
        y["cleared"] += r["cleared_mwh"]
        y["delivered"] += r["delivered_mwh"]
        y["events"] += 1

    return {
        "records": len(recs),
        "event_days": len({r["date"] for r in recs}),
        "years": sorted({r["year"] for r in recs}),
        "bid_mwh": round(bid, 1),
        "cleared_mwh": round(cleared, 1),
        "delivered_mwh": round(delivered, 1),
        "clearing_rate": round(cleared / bid, 4) if bid else None,
        "delivery_rate": round(delivered / cleared, 4) if cleared else None,
        "delivery_pct_mean": round(statistics.mean(rates), 1),
        "delivery_pct_median": round(statistics.median(rates), 1),
        "full_delivery_share": round(sum(1 for x in rates if x >= 100) / len(rates), 3),
        "smp_mean": round(statistics.mean(smp), 1) if smp else None,
        "smp_min": round(min(smp), 1) if smp else None,
        "smp_max": round(max(smp), 1) if smp else None,
        "smp_below_60_share": round(sum(1 for s in smp if s <= 60) / len(smp), 3) if smp else None,
        "hour_hist": dict(sorted(hours.items())),
        "by_year": {k: {kk: round(vv, 1) for kk, vv in v.items()} for k, v in per_year.items()},
    }


# ── 3. 재생에너지 예측 정확도 ──────────────────────────────

def ingest_re_forecast() -> dict:
    """예측 대비 실적 → 하루전 예측오차 검증."""
    p = RAW / "re_forecast_raw.csv"
    if not p.exists():
        return {}
    out = {}
    for r in _read(p):
        src = (r.get("발전원") or "").strip()
        fp, ap = _num(r.get("예측최대출력(MW)")), _num(r.get("실적최대출력(MW)"))
        fa, aa = _num(r.get("예측평균출력(MW)")), _num(r.get("실적평균출력(MW)"))
        if not src or fp is None or ap is None:
            continue
        out[src] = {
            "peak_forecast_mw": fp, "peak_actual_mw": ap,
            "peak_error": round((ap - fp) / fp, 4) if fp else None,
            "mean_forecast_mw": fa, "mean_actual_mw": aa,
            "mean_error": round((aa - fa) / fa, 4) if fa else None,
        }
    errs = [abs(v["peak_error"]) for v in out.values() if v.get("peak_error") is not None]
    out["_implied_forecast_error"] = round(statistics.mean(errs), 4) if errs else None
    return out


# ── 4. 제주 수급실적 ───────────────────────────────────────

def ingest_supply() -> dict:
    """제주 전력수급실적 xlsx → 설비·공급능력·최대전력 수준."""
    files = sorted(RAW.glob("powerDemandPerformJeju_*.xlsx"))
    if not files:
        return {}
    try:
        import openpyxl
    except ImportError:
        return {"error": "openpyxl 미설치 — pip install openpyxl"}

    rows = []
    for p in files:
        wb = openpyxl.load_workbook(p, data_only=True)
        for r in wb.active.iter_rows(min_row=4, values_only=True):
            if not r or r[1] is None:
                continue
            cap, supply, peak = _num(r[2]), _num(r[3]), _num(r[5])
            if peak is None:
                continue
            rows.append({"ts": str(r[1]), "capacity_mw": cap,
                         "supply_mw": supply, "peak_mw": peak,
                         "reserve_pct": _num(r[8])})
    if not rows:
        return {}
    peaks = [r["peak_mw"] for r in rows if r["peak_mw"]]
    caps = [r["capacity_mw"] for r in rows if r["capacity_mw"]]
    sup = [r["supply_mw"] for r in rows if r["supply_mw"]]
    return {
        "months": [p.stem.split("_")[-1] for p in files],
        "samples": len(rows),
        "capacity_mw": round(statistics.mean(caps), 1) if caps else None,
        "supply_mw_mean": round(statistics.mean(sup), 1) if sup else None,
        "peak_mw_mean": round(statistics.mean(peaks), 1),
        "peak_mw_max": round(max(peaks), 1),
        "peak_mw_min": round(min(peaks), 1),
    }


def main() -> int:
    if not RAW.exists():
        print(f"원본 폴더가 없습니다: {RAW}")
        return 1

    facts = {
        "source": "한국전력거래소 공공데이터 (출력제어·플러스DR·신재생예측·수급실적)",
        "curtailment": ingest_curtailment(),
        "plus_dr": ingest_plusdr(),
        "re_forecast": ingest_re_forecast(),
        "supply": ingest_supply(),
    }

    c, d = facts["curtailment"], facts["plus_dr"]
    facts["headline"] = {
        "curtail_days_per_year": c.get("days_per_year"),
        "curtail_day_share": c.get("day_share"),
        "clearing_rate": d.get("clearing_rate"),
        "delivery_rate": d.get("delivery_rate"),
        "smp_at_event_mean": d.get("smp_mean"),
        "note": (
            "출력제어 시각에도 제주 SMP는 평균 "
            f"{d.get('smp_mean')}원이다. 남는 전력을 싸게 사는 메커니즘은 없다. "
            "대신 플러스 DR이 별도 인센티브로 수요를 끌어올린다. "
            f"낙찰률 {(d.get('clearing_rate') or 0) * 100:.0f}% — 경쟁이 없고, "
            f"이행률 {(d.get('delivery_rate') or 0) * 100:.0f}% — 낙찰자도 지키지 못한다. "
            "배터리는 지킬 수 있다. 그 격차가 사업 기회다."
        ),
    }

    (OUT / "jeju_facts.json").write_text(
        json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")

    print("적재 완료")
    print(f"  출력제어 : {c.get('event_days')}일 · {c.get('total_mwh'):,}MWh · "
          f"연 {c.get('days_per_year')}일 · 주요시간 {c.get('top_hours')}")
    print(f"  플러스DR : {d.get('records')}건 / {d.get('event_days')}일 · "
          f"낙찰률 {(d.get('clearing_rate') or 0) * 100:.0f}% · "
          f"이행률 {(d.get('delivery_rate') or 0) * 100:.1f}%")
    print(f"  이벤트 SMP: 평균 {d.get('smp_mean')} (최저 {d.get('smp_min')})")
    print(f"  예측오차 : {facts['re_forecast'].get('_implied_forecast_error')}")
    print(f"  수급실적 : 최대전력 평균 {facts['supply'].get('peak_mw_mean')}MW")
    print(f"\n  → {OUT / 'jeju_facts.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

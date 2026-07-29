"""KPX 시간별 SMP·수요 이력 수집기 — 백테스트의 마지막 합성을 걷어낸다.

── 왜 필요한가 ────────────────────────────────────────────────

백테스트는 지금까지 이런 합성 가격으로 돌았다.

    MCP(t) = 한전 요금(t) × (0.95 + 0.55 × 수요백분위(t)²)

원재료(요금표·수요)는 실측이지만 결과물은 **실제 시장 체결가가 아니다.**
KPX API에 시간별 SMP가 육지·제주 각각 115,296행(약 6.6년) 들어 있다.
이걸 받아두면 백테스트가 실측 위에서 돈다.

── 설계를 지배하는 제약: 하루 100회 ──────────────────────────

    1회 호출 = 최대 1,000행 (numOfRows 상한)
    전체 115,296행 → 약 116회 → 이틀치 할당량

그래서 이렇게 만든다.

    * **중단·재개 가능** — 어디까지 받았는지 파일에 기록한다
    * **할당량 자동 정지** — 남은 횟수를 넘기지 않는다
    * **누적 저장** — 실행할 때마다 기존 데이터에 덧붙인다
    * **최신부터** — 페이지 1이 최신이므로 중간에 멈춰도 쓸모 있는 구간이 남는다

실행 (국내 PC에서 — 해외 IP는 차단된다):
    cd backend
    set KPX_API_KEY=발급받은키
    python scripts/fetch_smp_history.py                 # 남은 할당량만큼
    python scripts/fetch_smp_history.py --max-calls 20  # 20회만
    python scripts/fetch_smp_history.py --stats         # 호출 없이 현황만

산출:
    data/kpx_smp_hourly.csv     date,hour,area,smp,jeju_load_mw,land_load_mw
    data/kpx_history_state.json 진행 상태 (다음 페이지·호출 이력)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[1]
OUT_CSV = ROOT / "data" / "kpx_smp_hourly.csv"
STATE = ROOT / "data" / "kpx_history_state.json"

API = "https://apis.data.go.kr/B552115/SmpWithForecastDemand/getSmpWithForecastDemand"
ROWS_PER_CALL = 1000        # 포털 상한
DEFAULT_QUOTA = 90          # 100에서 여유를 남긴다
FIELDS = ["date", "hour", "area", "smp", "jeju_load_mw", "land_load_mw"]


# ── 상태 ───────────────────────────────────────────────────

def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"next_page": 1, "total_count": None, "calls": {}, "rows": 0}


def save_state(s: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def today() -> str:
    return datetime.now(KST).strftime("%Y%m%d")


def calls_today(s: dict) -> int:
    return int(s.get("calls", {}).get(today(), 0))


# ── 수집 ───────────────────────────────────────────────────

def fetch_page(key: str, page: int) -> tuple[list[dict], int]:
    """한 페이지 수집 → (행 목록, totalCount)."""
    params = {
        "serviceKey": key, "returnType": "json", "dataType": "JSON",
        "numOfRows": str(ROWS_PER_CALL), "pageNo": str(page),
        "tradeDay": today(),
    }
    with httpx.Client(timeout=40.0, follow_redirects=True) as c:
        r = c.get(API, params=params)
        r.raise_for_status()
        p = r.json()

    resp = (p or {}).get("response") or {}
    head = resp.get("header") or {}
    if str(head.get("resultCode", "")).strip() not in ("00", "0", ""):
        raise SystemExit(f"API 오류: {head.get('resultCode')} {head.get('resultMsg')}")

    body = resp.get("body") or {}
    items = (body.get("items") or {}).get("item") or []
    if isinstance(items, dict):
        items = [items]
    try:
        total = int(body.get("totalCount") or 0)
    except (TypeError, ValueError):
        total = 0
    return [i for i in items if isinstance(i, dict)], total


def normalize(rows: list[dict]) -> list[dict]:
    """응답 → CSV 스키마. 지역은 그대로 보존한다(육지·제주 둘 다 쓴다)."""
    def num(v):
        try:
            return float(str(v).replace(",", "").strip())
        except (TypeError, ValueError):
            return None

    out = []
    for r in rows:
        d = str(r.get("date") or "").strip()
        h = r.get("hour")
        if not d or h is None:
            continue
        out.append({
            "date": d,
            "hour": int(h),
            "area": str(r.get("areaName") or "").strip(),
            "smp": num(r.get("smp")),
            "jeju_load_mw": num(r.get("jlfd")),
            "land_load_mw": num(r.get("mlfd")),
        })
    return out


def load_existing() -> dict[tuple, dict]:
    """기존 CSV → 키(date,hour,area) 사전. 중복 방지용."""
    if not OUT_CSV.exists():
        return {}
    out = {}
    with OUT_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[(r["date"], r["hour"], r["area"])] = r
    return out


def write_all(recs: dict[tuple, dict]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(recs.values(), key=lambda r: (r["date"], int(r["hour"]), r["area"]))
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


# ── 현황 ───────────────────────────────────────────────────

def stats() -> None:
    s = load_state()
    recs = load_existing()
    print(f"수집 상태 — 다음 페이지 {s.get('next_page')} / "
          f"전체 {s.get('total_count') or '?'}행")
    print(f"오늘 호출 {calls_today(s)}회")
    if not recs:
        print("아직 수집된 데이터가 없습니다.")
        return

    by_area = defaultdict(list)
    for (d, _h, a), r in recs.items():
        if r.get("smp"):
            by_area[a].append((d, float(r["smp"])))
    print(f"보유 {len(recs):,}행 · 파일 {OUT_CSV}")
    for a, vals in sorted(by_area.items()):
        days = {d for d, _ in vals}
        prices = [v for _, v in vals]
        print(f"  {a:<4} {len(vals):>7,}행 · {len(days):>5}일 "
              f"({min(days)}~{max(days)}) · SMP 평균 {sum(prices) / len(prices):.1f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-calls", type=int, default=0, help="이번 실행 호출 상한")
    ap.add_argument("--quota", type=int,
                    default=int(os.environ.get("KPX_SMP_QUOTA", DEFAULT_QUOTA)))
    ap.add_argument("--stats", action="store_true", help="호출 없이 현황만")
    args = ap.parse_args()

    if args.stats:
        stats()
        return 0

    key = os.environ.get("KPX_API_KEY", "").strip()
    if not key:
        print("KPX_API_KEY 환경변수가 없습니다.")
        return 1

    s = load_state()
    used = calls_today(s)
    budget = max(0, args.quota - used)
    if args.max_calls > 0:
        budget = min(budget, args.max_calls)
    if budget <= 0:
        print(f"오늘 할당량 소진 ({used}/{args.quota}). 내일 이어서 받으세요.")
        stats()
        return 0

    recs = load_existing()
    page = int(s.get("next_page", 1))
    total = s.get("total_count")
    added = 0

    print(f"수집 시작 — 페이지 {page}부터 · 이번 실행 최대 {budget}회 "
          f"(오늘 {used}/{args.quota} 사용)")

    for i in range(budget):
        try:
            rows, tc = fetch_page(key, page)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"  p{page} 실패: {exc}")
            break

        s.setdefault("calls", {})[today()] = calls_today(s) + 1
        if tc:
            total = tc
        if not rows:
            print(f"  p{page} 빈 페이지 — 수집 종료")
            page += 1
            break

        new = 0
        for r in normalize(rows):
            k = (r["date"], str(r["hour"]), r["area"])
            if k not in recs:
                recs[k] = r
                new += 1
        added += new
        print(f"  p{page:>4} · {len(rows):>4}행 수신 · 신규 {new:>4} · 누적 {len(recs):,}")
        page += 1

        if total and (page - 1) * ROWS_PER_CALL >= total:
            print("  마지막 페이지 도달")
            break

    s["next_page"] = page
    s["total_count"] = total
    s["rows"] = len(recs)
    save_state(s)
    write_all(recs)

    print(f"\n저장 완료 — 신규 {added:,}행 · 누적 {len(recs):,}행")
    print(f"  {OUT_CSV}")
    if total:
        done = min(100.0, (page - 1) * ROWS_PER_CALL / total * 100)
        print(f"  진행률 {done:.1f}% (다음 실행은 페이지 {page}부터)")
    print()
    stats()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""KPX SMP 실데이터 적재 — 제주/육지 월별 가중평균 → 시장 엔진 보정.

입력: 전력거래소에서 내려받은 계통한계가격 CSV
      (헤더 2줄: `기간,SMP,,,BLMP` / `,육지,제주,통합,`, 인코딩 CP949)

산출:
  1. data/kpx_smp_monthly.csv  — 정규화 (year,month,land,jeju,total)
  2. data/kpx_calibration.json — 제주 보정 계수 (월별 + 최근 12개월 평균)

왜 필요한가:
  우리 백테스트 가격엔진은 육지 기준 재생 데이터로 돌아간다.
  제주는 재생에너지 비중이 높아 가격 수준과 계절성이 다르다.
  이 스크립트가 뽑은 **월별 제주/육지 비율**을 곱하면,
  시간대별 형상은 유지하면서 제주 가격 수준으로 보정할 수 있다.

  ※ 시간대별 실제 곡선(제주)은 EPSIS에서 별도로 받아야 한다.
    여기서 하는 건 '수준·계절성 보정'이지 '시간별 실측 대체'가 아니다.

실행:
    python scripts/ingest_kpx_smp.py data/kpx_smp_monthly_raw.csv
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_CSV = ROOT / "data" / "kpx_smp_monthly.csv"
OUT_JSON = ROOT / "data" / "kpx_calibration.json"


def read_raw(path: Path) -> list[dict]:
    """2줄 헤더 + CP949 형식을 읽어 정규화."""
    text = None
    for enc in ("cp949", "utf-8-sig", "utf-8"):
        try:
            text = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise SystemExit(f"인코딩을 판별하지 못했습니다: {path}")

    lines = [l for l in text.splitlines() if l.strip()]
    rows: list[dict] = []
    for line in lines:
        cells = [c.strip() for c in line.split(",")]
        if not cells or not re.match(r"^\d{4}[/.-]\d{1,2}$", cells[0]):
            continue          # 헤더·주석 줄 건너뛰기
        y, m = re.split(r"[/.-]", cells[0])

        def num(i: int) -> float | None:
            try:
                v = float(cells[i])
                return v if v > 0 else None      # 0은 미집계(제주 초기 구간)
            except (IndexError, ValueError):
                return None

        rows.append({
            "year": int(y), "month": int(m),
            "land": num(1), "jeju": num(2), "total": num(3),
        })
    return sorted(rows, key=lambda r: (r["year"], r["month"]))


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "kpx_smp_monthly_raw.csv"
    if not src.exists():
        print(f"입력 파일이 없습니다: {src}")
        return 1

    rows = read_raw(src)
    if not rows:
        print("파싱된 행이 없습니다. 파일 형식을 확인해주세요.")
        return 1

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["year", "month", "land", "jeju", "total"])
        w.writeheader()
        w.writerows(rows)

    both = [r for r in rows if r["land"] and r["jeju"]]
    ratios = [r["jeju"] / r["land"] for r in both]

    # 월(1~12)별 평균 비율 — 계절성 보정용
    by_month: dict[int, list[float]] = {}
    for r in both:
        by_month.setdefault(r["month"], []).append(r["jeju"] / r["land"])
    monthly = {str(m): round(statistics.mean(v), 4) for m, v in sorted(by_month.items())}

    recent = both[-12:]
    recent_ratio = statistics.mean(r["jeju"] / r["land"] for r in recent)

    calib = {
        "source": src.name,
        "months": len(rows),
        "period": f"{rows[0]['year']}-{rows[0]['month']:02d} ~ {rows[-1]['year']}-{rows[-1]['month']:02d}",
        "jeju_over_land_all": round(statistics.mean(ratios), 4),
        "jeju_over_land_recent12": round(recent_ratio, 4),
        "monthly_ratio": monthly,
        "recent12_jeju_mean": round(statistics.mean(r["jeju"] for r in recent), 2),
        "recent12_land_mean": round(statistics.mean(r["land"] for r in recent), 2),
        "note": "제주 시간대별 실측 곡선은 EPSIS에서 별도 수집. 이 값은 수준·계절성 보정용.",
    }
    OUT_JSON.write_text(json.dumps(calib, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"적재 완료 — {len(rows)}개월 ({calib['period']})")
    print(f"  정규화 CSV : {OUT_CSV}")
    print(f"  보정 계수  : {OUT_JSON}")
    print(f"\n제주/육지 비율 — 전체 {calib['jeju_over_land_all']} · 최근 12개월 {calib['jeju_over_land_recent12']}")
    print(f"최근 12개월 평균 — 제주 ₩{calib['recent12_jeju_mean']} / 육지 ₩{calib['recent12_land_mean']}")
    peak = max(monthly, key=lambda k: monthly[k])
    low = min(monthly, key=lambda k: monthly[k])
    print(f"계절성 — 제주 프리미엄이 가장 큰 달 {peak}월({monthly[peak]}), 가장 작은 달 {low}월({monthly[low]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

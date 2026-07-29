"""오늘의 시간별 SMP(육지)를 KPX 웹에서 받아 data/kpx_smp.csv 로 저장.

Railway는 해외 IP라 한국 공공 API·KPX 접근이 막히므로, **한국 IP인 PC에서**
이 스크립트를 돌려 CSV를 만들고 커밋/배포하는 것이 실데이터 경로다
(kpx_feed.py 의 파일데이터 우회와 동일한 원칙).

출처: 한국전력거래소 육지 SMP 페이지 (로그인 불필요, 매일 갱신)
      https://www.kpx.or.kr/smpInland.es?mid=a10404080100
      — 최근 7일 × 24시간 표. 마지막 컬럼(오늘)을 뽑는다.

실행 (시연 전날/당일, 저장소 루트에서):
    py backend/scripts/fetch_kpx_smp_today.py
    → backend/data/kpx_smp.csv 갱신 → 커밋·푸시하면 Railway가 읽는다.

소비처:
  - backend 아파트 관제: kepco_service (SMP KPI, 육지 컬럼)
  - backend VPP 시장: kpx_feed (KPX_REGION=jeju면 제주 보정 배수 적용)
"""

from __future__ import annotations

import html
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

URL = "https://www.kpx.or.kr/smpInland.es?mid=a10404080100&device=pc"
OUT = Path(__file__).resolve().parents[1] / "data" / "kpx_smp.csv"
KST = timezone(timedelta(hours=9))


def main() -> int:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        text = resp.read().decode("utf-8", errors="replace")

    dates = re.findall(r'<th scope="col">\s*(\d{2}\.\d{2})', text)
    if not dates:
        print("날짜 헤더를 찾지 못했습니다 — KPX 페이지 구조가 바뀌었을 수 있습니다.")
        return 1

    today = datetime.now(KST).strftime("%m.%d")
    if dates[-1] != today:
        # 자정 직후 등 오늘 컬럼이 아직 없으면 마지막 날짜를 쓰되 경고한다
        print(f"주의: 마지막 컬럼이 오늘({today})이 아니라 {dates[-1]} 입니다. 그대로 저장합니다.")
    col = len(dates) - 1

    rows = re.findall(r"<tr>\s*<t[hd][^>]*>\s*([^<]+?)\s*</t[hd]>(.*?)</tr>", text, re.S)
    curve: dict[int, float] = {}
    for label, cells in rows:
        m = re.fullmatch(r"(\d{1,2})h", html.unescape(label).strip())
        if not m:
            continue
        vals = re.findall(r"<td[^>]*>\s*([^<]*?)\s*</td>", cells)
        if len(vals) <= col:
            continue
        raw = vals[col].replace(",", "").strip()
        if raw:
            curve[int(m.group(1))] = float(raw)

    if len(curve) < 24:
        print(f"24시간 중 {len(curve)}개만 파싱됨 — 저장하지 않습니다.")
        return 1

    lines = ["시간,SMP(육지)"] + [f"{h},{curve[h]}" for h in range(1, 25)]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print(f"저장 완료: {OUT} ({dates[col]} 육지 SMP, 1~24h, "
          f"최소 {min(curve.values())} / 최대 {max(curve.values())} 원/kWh)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

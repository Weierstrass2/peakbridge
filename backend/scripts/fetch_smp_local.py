"""국내 PC에서 KPX SMP를 받아 배포 서버로 밀어 넣는다.

── 왜 필요한가 ────────────────────────────────────────────────

공공데이터포털(apis.data.go.kr)은 해외 IP에서 접속이 막히거나 매우 느리다.
Railway 배포 서버가 해외에 있어 직접 호출하면 ConnectTimeout이 난다.

    [Railway·해외]  ──X──> apis.data.go.kr
    [내 PC·국내]    ──O──> apis.data.go.kr ──> POST /smp-api/inject ──> [Railway]

주입 경로는 직접 호출과 **같은 파서·같은 캐시**를 타므로 결과물의 신뢰도는 동일하다.

실행 (국내 PC에서):
    cd backend
    set KPX_API_KEY=발급받은키
    python scripts/fetch_smp_local.py
    python scripts/fetch_smp_local.py --dry     # 서버 전송 없이 응답만 확인

환경변수:
    KPX_API_KEY   공공데이터포털 일반 인증키 (Decoding)
    BACKEND_URL   배포 서버 (기본 Railway)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx

KST = timezone(timedelta(hours=9))
API = "https://apis.data.go.kr/B552115/SmpWithForecastDemand/getSmpWithForecastDemand"
DEFAULT_BACKEND = "https://peakbridge-production.up.railway.app"


# 공공데이터포털은 서비스마다 날짜 파라미터 이름이 제각각이다.
# 문서를 못 볼 때는 후보를 순서대로 시도한다 (성공하면 즉시 멈춘다).
DATE_KEYS = ["tradeDay", "baseDate", "tradeDd", "stdDt", "searchDate", "dataDate", "baseDt"]


def _ok(payload: dict) -> bool:
    """정상 응답인가 — resultCode 00 이고 body 가 있으면 성공."""
    h = ((payload or {}).get("response") or {}).get("header") or {}
    body = ((payload or {}).get("response") or {}).get("body")
    code = str(h.get("resultCode", "")).strip()
    return body is not None and code in ("00", "0", "")


def _msg(payload: dict) -> str:
    h = ((payload or {}).get("response") or {}).get("header") or {}
    return f"{h.get('resultCode', '?')} {h.get('resultMsg', '')}".strip()


def fetch(key: str, day: str | None = None) -> dict:
    """KPX 응답 원본을 그대로 가져온다 (가공하지 않는다).

    날짜 파라미터 이름을 모르므로 후보를 차례로 시도한다.
    각 시도가 일일 할당량(100회)을 1회씩 소모하므로 성공하면 바로 멈춘다.
    """
    targets = [day] if day else [
        (datetime.now(KST) + timedelta(days=1)).strftime("%Y%m%d"),   # 내일 (하루전 계획)
        datetime.now(KST).strftime("%Y%m%d"),                         # 오늘
    ]
    base = {"serviceKey": key, "returnType": "json", "dataType": "JSON",
            "numOfRows": "200", "pageNo": "1"}

    tried = []
    with httpx.Client(timeout=30.0, follow_redirects=True) as c:
        for target in targets:
            for dk in DATE_KEYS:
                params = {**base, dk: target}
                r = c.get(API, params=params)
                try:
                    payload = r.json()
                except Exception:  # noqa: BLE001
                    print(f"  {dk}={target} → JSON 아님: {r.text[:120]}")
                    tried.append(f"{dk}(비JSON)")
                    continue
                if _ok(payload):
                    print(f"성공 — 파라미터 '{dk}={target}'")
                    return payload
                m = _msg(payload)
                print(f"  {dk}={target} → {m}")
                tried.append(f"{dk}({m[:20]})")
                # 파라미터 이름은 맞고 날짜만 없는 경우엔 다음 날짜로 넘어간다
                if "없습니다" not in m and "파라메터" not in m and "파라미터" not in m:
                    break

    raise SystemExit(
        "모든 후보 실패. 포털 '상세기능정보 → 요청변수'에서 필수 파라미터명을 확인하세요.\n"
        f"시도: {', '.join(tried)}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", help="YYYYMMDD (기본: 내일)")
    ap.add_argument("--dry", action="store_true", help="서버 전송 없이 응답만 출력")
    ap.add_argument("--backend", default=os.environ.get("BACKEND_URL", DEFAULT_BACKEND))
    args = ap.parse_args()

    key = os.environ.get("KPX_API_KEY", "").strip()
    if not key:
        print("KPX_API_KEY 환경변수가 없습니다.")
        return 1

    payload = fetch(key, args.day)
    head = json.dumps(payload, ensure_ascii=False)[:500]
    print(f"\n--- 응답 구조 ---\n{head}\n")

    if args.dry:
        print("(--dry — 서버 전송 생략)")
        return 0

    url = f"{args.backend.rstrip('/')}/api/v1/market/smp-api/inject"
    with httpx.Client(timeout=20.0) as c:
        r = c.post(url, json=payload)
        r.raise_for_status()
        out = r.json().get("data", {})

    if out.get("ok"):
        print(f"주입 성공 — SMP {out['smp'][:4]} …")
        if out.get("demand"):
            print(f"           수요 {out['demand'][:4]} …")
    else:
        print(f"주입 실패 — {out.get('error')}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

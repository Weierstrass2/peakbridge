"""당일 SMP 자동 중계 — KPX 웹의 하루전 확정가를 긁어 클라우드에 주입한다.

Railway(해외 IP)는 한국 공공 API·KPX 웹에 직접 접근하지 못한다. 시연 때 항상
켜 두는 이 로컬 서버(한국 IP)가 대신 받아, 기존 주입 경로
(POST /api/v1/market/smp-api/inject)로 밀어 넣는다. 그러면:

  - 아파트 관제 SMP 카드(kepco_service)가 당일 확정가로 갱신 (출처 "inject")
  - VPP 콘솔의 SMP 곡선(kpx_smp_api 캐시)도 함께 갱신
  - CSV 커밋·재배포 불필요

KPX 페이지는 로그인·키 없이 공개돼 있다 (최근 7일 × 24시간 표, 마지막 컬럼이 오늘).
육지·제주를 모두 보내며, 주입 파서(_to_curve)가 지역·날짜로 걸러 저장한다.

원칙: bridge.py와 동일하게 BRIDGE_URL이 설정된 경우에만 동작하고,
      실패가 로컬 시연을 절대 방해하지 않는다 (데몬 스레드, 로그만).

주기: 성공 시 6시간(SMP는 하루 단위 확정이라 충분), 실패 시 30분 후 재시도.
"""

import logging
import os
import re
import threading
import urllib.request
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("smp_relay")
KST = timezone(timedelta(hours=9))

PAGES = [
    ("육지", "https://www.kpx.or.kr/smpInland.es?mid=a10404080100&device=pc"),
    ("제주", "https://www.kpx.or.kr/smpJeju.es?mid=a10404080200&device=pc"),
]
OK_INTERVAL_S = 6 * 3600
RETRY_INTERVAL_S = 30 * 60

_enabled = False
_url = ""
_last_ok: str | None = None   # 마지막 성공 주입 시각 (KST isoformat)
_last_error = ""


def status() -> dict:
    return {"enabled": _enabled, "last_ok": _last_ok, "last_error": _last_error}


def init() -> None:
    global _enabled, _url
    _url = os.environ.get("BRIDGE_URL", "").strip().rstrip("/")
    if not _url:
        logger.info("BRIDGE_URL 미설정 — SMP 중계 비활성 (로컬 시연에는 불필요).")
        return
    _enabled = True
    threading.Thread(target=_run, daemon=True).start()
    logger.info("SMP 중계 활성: KPX 웹 → %s/api/v1/market/smp-api/inject", _url)


def _scrape(url: str) -> tuple[str, dict[int, float]]:
    """KPX 페이지 → (날짜 YYYYMMDD, {1~24h: 원/kWh}). 마지막 컬럼 = 최신일."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        text = resp.read().decode("utf-8", errors="replace")

    dates = re.findall(r'<th scope="col">\s*(\d{2}\.\d{2})', text)
    if not dates:
        raise ValueError("날짜 헤더 없음 — 페이지 구조 변경 가능성")
    col = len(dates) - 1

    now = datetime.now(KST)
    month, day = (int(x) for x in dates[col].split("."))
    # 연말·연초 걸침 보정 (12월 컬럼을 1월에 보는 경우)
    year = now.year - 1 if month > now.month + 6 else now.year
    date_str = f"{year}{month:02d}{day:02d}"

    curve: dict[int, float] = {}
    rows = re.findall(r"<tr>\s*<t[hd][^>]*>\s*([^<]+?)\s*</t[hd]>(.*?)</tr>", text, re.S)
    for label, cells in rows:
        m = re.fullmatch(r"(\d{1,2})h", label.strip())
        if not m:
            continue
        vals = re.findall(r"<td[^>]*>\s*([^<]*?)\s*</td>", cells)
        if len(vals) <= col:
            continue
        raw = vals[col].replace(",", "").strip()
        if raw:
            curve[int(m.group(1))] = float(raw)
    if len(curve) < 24:
        raise ValueError(f"24시간 중 {len(curve)}개만 파싱됨")
    return date_str, curve


def relay_once() -> bool:
    """KPX 육지·제주를 긁어 1회 주입. 성공 여부 반환 (테스트에서도 사용)."""
    global _last_ok, _last_error
    import requests

    items: list[dict] = []
    for area, url in PAGES:
        try:
            date_str, curve = _scrape(url)
            items += [
                {"date": date_str, "hour": h, "areaName": area, "smp": v}
                for h, v in curve.items()
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("KPX %s 페이지 수집 실패: %s", area, exc)
    if not items:
        _last_error = "KPX 페이지 수집 전멸"
        return False

    try:
        resp = requests.post(
            f"{_url}/api/v1/market/smp-api/inject",
            json={"items": items},
            timeout=10,
        )
        ok = resp.status_code < 400 and (resp.json().get("data") or {}).get("ok") is True
        if ok:
            _last_ok = datetime.now(KST).isoformat(timespec="seconds")
            _last_error = ""
            logger.info("SMP 주입 성공 (%d행, %s)", len(items), items[0]["date"])
        else:
            _last_error = f"주입 거부: {resp.text[:160]}"
            logger.warning("SMP 주입 실패: %s", _last_error)
        return ok
    except Exception as exc:  # noqa: BLE001
        _last_error = str(exc)[:160]
        logger.warning("SMP 주입 예외: %s", _last_error)
        return False


def _run() -> None:
    import time

    while True:
        ok = relay_once()
        time.sleep(OK_INTERVAL_S if ok else RETRY_INTERVAL_S)

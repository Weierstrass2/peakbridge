"""KPX 계통한계가격·수요예측 API 클라이언트 (하루전 발전계획용).

    End Point : https://apis.data.go.kr/B552115/SmpWithForecastDemand
    기능      : /getSmpWithForecastDemand — 1시간 단위 SMP + 수요예측
    일일 트래픽: **100회**

── 이 파일의 설계를 지배하는 것은 '하루 100회' 제약이다 ──────────

콘솔 스트림은 3초마다 돈다. 거기에 그대로 물리면 5분 만에 할당량이 끝난다.
그래서 다음 원칙을 강제한다.

  1. **하루 1회면 충분하다.** 이 데이터는 '하루전 발전계획'이다.
     내일치 24시간 곡선이 한 번 확정되면 그날은 바뀌지 않는다.
  2. **스트림 경로에서 절대 호출하지 않는다.** 캐시만 읽는다.
  3. **호출 횟수를 파일에 기록한다.** 서버가 재시작해도 카운터가 살아 있어야
     하루 100회를 지킬 수 있다.
  4. **실패해도 마지막 성공값을 유지한다.** 현장 인터넷이 끊겨도 화면이 안 빈다.

환경변수:
    KPX_API_KEY    공공데이터포털 일반 인증키 (Decoding)
    KPX_SMP_QUOTA  일일 호출 상한 (기본 90 — 100에서 여유 10 남김)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)
KST = timezone(timedelta(hours=9))

BASE = "https://apis.data.go.kr/B552115/SmpWithForecastDemand"
PATH = "getSmpWithForecastDemand"

CACHE = Path(__file__).resolve().parents[2] / "data" / "kpx_smp_api_cache.json"
DEFAULT_QUOTA = 90          # 100에서 여유를 남긴다
# data.go.kr은 해외 IP에서 접속이 매우 느리거나 막힌다.
# Railway 서버가 해외에 있으면 ConnectTimeout이 난다 — 그때는
# 국내에서 받아 온 곡선을 POST /smp-api/inject 로 밀어 넣는 경로를 쓴다.
TIMEOUT_S = 25.0


class SmpForecastApi:
    """하루전 SMP·수요예측 — 하루 1회 호출, 나머지는 캐시."""

    def __init__(self) -> None:
        self._mem: dict | None = None

    # ── 상태 ──
    @property
    def enabled(self) -> bool:
        return bool(os.environ.get("KPX_API_KEY", "").strip())

    @property
    def quota(self) -> int:
        try:
            return int(os.environ.get("KPX_SMP_QUOTA", DEFAULT_QUOTA))
        except ValueError:
            return DEFAULT_QUOTA

    def _load_cache(self) -> dict:
        if self._mem is not None:
            return self._mem
        try:
            self._mem = json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            self._mem = {}
        return self._mem

    def _save_cache(self, d: dict) -> None:
        self._mem = d
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("kpx_smp_cache_write_failed", error=str(exc))

    def _today(self) -> str:
        return datetime.now(KST).strftime("%Y%m%d")

    def calls_today(self) -> int:
        c = self._load_cache()
        return int(c.get("calls", {}).get(self._today(), 0))

    def _bump(self) -> None:
        c = self._load_cache()
        calls = c.setdefault("calls", {})
        t = self._today()
        calls[t] = int(calls.get(t, 0)) + 1
        # 최근 7일만 보관
        for k in sorted(calls)[:-7]:
            calls.pop(k, None)
        self._save_cache(c)

    def status(self) -> dict:
        c = self._load_cache()
        cur = c.get("curve") or {}
        return {
            "enabled": self.enabled,
            "endpoint": f"{BASE}/{PATH}",
            "calls_today": self.calls_today(),
            "quota": self.quota,
            "remaining": max(0, self.quota - self.calls_today()),
            "cached_date": cur.get("date"),
            "has_smp": bool(cur.get("smp")),
            "has_demand": bool(cur.get("demand")),
            "last_error": c.get("last_error", ""),
            "diagnostic": c.get("diagnostic"),
            "fetched_at": cur.get("fetched_at"),
        }

    # ── 파싱 ──
    @staticmethod
    def _rows(payload: Any) -> list[dict]:
        """data.go.kr 계열의 여러 응답 형태를 흡수한다.

        {response:{body:{items:{item:[...]}}}} / {items:[...]} / [...] 모두 대응.
        """
        if isinstance(payload, list):
            return [r for r in payload if isinstance(r, dict)]
        if not isinstance(payload, dict):
            return []
        for path in (
            ("response", "body", "items", "item"),
            ("response", "body", "items"),
            ("body", "items", "item"),
            ("items", "item"),
            ("items",),
            ("data",),
        ):
            cur: Any = payload
            for k in path:
                if not isinstance(cur, dict) or k not in cur:
                    cur = None
                    break
                cur = cur[k]
            if isinstance(cur, list) and cur and isinstance(cur[0], dict):
                return cur
            if isinstance(cur, dict):
                return [cur]
        return []

    @staticmethod
    def _pick(row: dict, *keys: str) -> float | None:
        """필드명이 개정돼도 키워드로 찾는다."""
        for k in keys:
            for rk, rv in row.items():
                if k.lower() in str(rk).lower():
                    try:
                        return float(str(rv).replace(",", "").strip())
                    except (TypeError, ValueError):
                        continue
        return None

    def _to_curve(self, rows: list[dict], region: str | None = None,
                  day: str | None = None) -> dict:
        """행 목록 → 24시간 SMP·수요 곡선.

        실제 응답 스키마 (확인됨):
            date "20260729" · hour 1~24 · areaName "육지"|"제주" · smp
            slfd 계통 전체 부하예측 · mlfd 육지 부하예측 · jlfd 제주 부하예측

        **지역과 날짜로 반드시 걸러야 한다.** 응답에는 여러 날·두 지역이 섞여 있어
        그냥 훑으면 뒤 행이 앞 행을 덮어써 곡선이 뒤섞인다.
        """
        want = (region or os.environ.get("KPX_REGION", "jeju")).strip().lower()
        area_kr = "제주" if want == "jeju" else "육지"
        # 제주면 jlfd, 육지면 mlfd 를 수요로 쓴다
        load_key = "jlfd" if want == "jeju" else "mlfd"

        # 날짜 미지정이면 응답에서 가장 최근 날짜를 고른다
        if day is None:
            days = {str(r.get("date") or "").strip() for r in rows}
            days.discard("")
            day = max(days) if days else None

        smp: dict[int, float] = {}
        dem: dict[int, float] = {}
        for r in rows:
            if day and str(r.get("date") or "").strip() != day:
                continue
            area = str(r.get("areaName") or "").strip()
            if area and area_kr not in area:
                continue
            h = self._pick(r, "hour", "시간", "hh", "time")
            if h is None:
                continue
            idx = int(h) - 1 if 1 <= int(h) <= 24 else int(h)
            if not 0 <= idx <= 23:
                continue
            s = self._pick(r, "smp", "계통한계", "price")
            d = r.get(load_key)
            if d is None:
                d = self._pick(r, "demand", "수요", "load")
            else:
                try:
                    d = float(str(d).replace(",", ""))
                except (TypeError, ValueError):
                    d = None
            if s is not None:
                smp[idx] = s
            if d is not None:
                dem[idx] = d

        def fill(m: dict[int, float]) -> list[float] | None:
            if len(m) < 6:
                return None
            out, last = [], next(iter(m.values()))
            for h in range(24):
                last = m.get(h, last)
                out.append(round(last, 2))
            return out

        return {"smp": fill(smp), "demand": fill(dem)}

    # ── 수집 ──
    async def refresh(self, force: bool = False) -> dict:
        """API 호출 — 하루 1회만. 할당량을 넘으면 캐시를 그대로 돌려준다."""
        cache = self._load_cache()
        cur = cache.get("curve") or {}
        today = self._today()

        if not force and cur.get("date") == today and cur.get("smp"):
            return cur                                  # 오늘치 이미 확보
        if not self.enabled:
            return cur
        if self.calls_today() >= self.quota:
            logger.warning("kpx_smp_quota_exceeded", calls=self.calls_today())
            cache["last_error"] = f"일일 할당량 소진 ({self.quota}회)"
            self._save_cache(cache)
            return cur

        key = os.environ.get("KPX_API_KEY", "").strip()
        # 공공데이터포털은 서비스마다 요청 날짜 파라미터 이름이 다르다.
        # 하루전 발전계획용이므로 '내일'을 기본으로 하되, 응답이 비면 오늘도 시도한다.
        now = datetime.now(KST)
        tomorrow = (now + timedelta(days=1)).strftime("%Y%m%d")
        params = {
            "serviceKey": key,
            "returnType": "json",
            "dataType": "JSON",
            "numOfRows": "200",
            "pageNo": "1",
            "baseDate": tomorrow,
            "tradeDay": tomorrow,
        }
        try:
            self._bump()
            async with httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=True) as c:
                r = await c.get(f"{BASE}/{PATH}", params=params)
                body = r.text or ""
                # 진단 정보를 항상 남긴다 — 할당량이 하루 90회뿐이라
                # 실패 한 번에서 최대한 많은 것을 알아내야 한다.
                diag = {
                    "http": r.status_code,
                    "content_type": r.headers.get("content-type", ""),
                    "length": len(body),
                    "body_head": body[:400],
                    "final_url": str(r.request.url).split("serviceKey=")[0] + "serviceKey=***",
                }
                cache["diagnostic"] = diag
                self._save_cache(cache)
                r.raise_for_status()
                if not body.strip():
                    raise ValueError(f"응답 본문이 비어 있음 (HTTP {r.status_code})")
                try:
                    payload = r.json()
                except Exception:  # noqa: BLE001
                    raise ValueError(f"JSON 아님 [{diag['content_type']}]: {body[:300]}")

            curve = self._to_curve(self._rows(payload))
            if not curve.get("smp"):
                raise ValueError(f"SMP 파싱 실패 — 응답: {str(payload)[:300]}")

            curve.update({"date": today,
                          "fetched_at": datetime.now(KST).isoformat(timespec="seconds")})
            cache["curve"] = curve
            cache["last_error"] = ""
            self._save_cache(cache)
            logger.info("kpx_smp_api_ok", smp_sample=curve["smp"][:3],
                        has_demand=bool(curve.get("demand")))
            return curve
        except Exception as exc:  # noqa: BLE001
            cache["last_error"] = (str(exc) or type(exc).__name__)[:300]
            self._save_cache(cache)
            logger.warning("kpx_smp_api_failed", error=cache["last_error"])
            return cur

    def inject(self, payload: Any) -> dict:
        """국내에서 받아 온 원본 응답을 그대로 밀어 넣는다.

        data.go.kr은 해외 IP에서 막히는 경우가 있어 Railway 서버가 직접 못 부른다.
        그럴 때는 **한국에서 받은 응답을 이 경로로 주입**한다.
        파싱·캐시 규칙은 직접 호출과 완전히 동일하므로 결과물의 신뢰도는 같다.
        """
        curve = self._to_curve(self._rows(payload))
        if not curve.get("smp"):
            return {"ok": False, "error": f"SMP 파싱 실패 — 응답: {str(payload)[:300]}"}
        cache = self._load_cache()
        curve.update({
            "date": self._today(),
            "fetched_at": datetime.now(KST).isoformat(timespec="seconds"),
            "via": "inject",          # 출처를 남긴다 (직접 호출과 구분)
        })
        cache["curve"] = curve
        cache["last_error"] = ""
        self._save_cache(cache)
        logger.info("kpx_smp_injected", smp_sample=curve["smp"][:3])
        return {"ok": True, "smp": curve["smp"], "demand": curve.get("demand")}

    def smp_curve(self) -> list[float] | None:
        """캐시된 24시간 SMP. **스트림 경로는 이것만 쓴다.**"""
        return (self._load_cache().get("curve") or {}).get("smp")

    def demand_curve(self) -> list[float] | None:
        """캐시된 24시간 수요예측. 피크 예약의 입력이 된다."""
        return (self._load_cache().get("curve") or {}).get("demand")


smp_api = SmpForecastApi()

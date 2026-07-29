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
TIMEOUT_S = 8.0


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

    def _to_curve(self, rows: list[dict]) -> dict:
        """행 목록 → 24시간 SMP·수요 곡선."""
        smp: dict[int, float] = {}
        dem: dict[int, float] = {}
        for r in rows:
            h = self._pick(r, "hour", "시간", "hh", "time")
            if h is None:
                continue
            idx = int(h) - 1 if int(h) >= 1 and int(h) <= 24 else int(h)
            if not 0 <= idx <= 23:
                continue
            s = self._pick(r, "smp", "계통한계", "price")
            d = self._pick(r, "demand", "수요", "load")
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
        params = {
            "serviceKey": key,
            "returnType": "json",
            "dataType": "JSON",
            "numOfRows": "100",
            "pageNo": "1",
        }
        try:
            self._bump()
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as c:
                r = await c.get(f"{BASE}/{PATH}", params=params)
                r.raise_for_status()
                try:
                    payload = r.json()
                except Exception:  # noqa: BLE001
                    raise ValueError(f"JSON 아님: {r.text[:200]}")

            curve = self._to_curve(self._rows(payload))
            if not curve.get("smp"):
                raise ValueError(f"SMP 파싱 실패 — 응답 키: {str(payload)[:200]}")

            curve.update({"date": today,
                          "fetched_at": datetime.now(KST).isoformat(timespec="seconds")})
            cache["curve"] = curve
            cache["last_error"] = ""
            self._save_cache(cache)
            logger.info("kpx_smp_api_ok", smp_sample=curve["smp"][:3],
                        has_demand=bool(curve.get("demand")))
            return curve
        except Exception as exc:  # noqa: BLE001
            cache["last_error"] = str(exc)[:200]
            self._save_cache(cache)
            logger.warning("kpx_smp_api_failed", error=cache["last_error"])
            return cur

    def smp_curve(self) -> list[float] | None:
        """캐시된 24시간 SMP. **스트림 경로는 이것만 쓴다.**"""
        return (self._load_cache().get("curve") or {}).get("smp")

    def demand_curve(self) -> list[float] | None:
        """캐시된 24시간 수요예측. 피크 예약의 입력이 된다."""
        return (self._load_cache().get("curve") or {}).get("demand")


smp_api = SmpForecastApi()

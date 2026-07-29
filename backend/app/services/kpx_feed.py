"""KPX 실데이터 피드 — 공공데이터포털 OpenAPI로 실제 SMP·수급을 받아온다.

데이터 경로 (2026-07 기준 실제 이용 가능 여부 반영):

  1. SMP — **CSV 파일데이터**로 받는다.
     계통한계가격 조회 OpenAPI는 "행정/공공기관 전용"이라 일반 신청이 거부된다.
     대신 공공데이터포털 파일데이터(시간별 계통한계가격)에 `시간 / SMP(육지) / SMP(제주)`가
     들어 있고 매일 갱신되며 로그인 없이 내려받을 수 있다.
     → 내려받은 CSV를 backend/data/ 에 두면 서버가 자동으로 읽는다 (KPX_SMP_CSV로 경로 지정 가능).
     → 제주/육지는 KPX_REGION 환경변수로 선택 (기본 jeju).

  2. 실시간 수급 — OpenAPI (자동승인)
     https://openapi.kpx.or.kr/openapi/sukub5mToday/getSukub5mToday

  3. 연료원별 SMP 결정횟수 — OpenAPI (자동승인, 제주/육지 구분)
     https://openapi.kpx.or.kr/openapi/smpFuelSourceDaily/getSmpFuelSourceDaily
     "오늘 제주 가격을 어떤 연료가 결정했는가"를 보여준다 —
     재생에너지 비중이 높은 제주 시장의 특성을 설명하는 근거가 된다.

설계 원칙:
  1. **키가 없어도 서버가 정상 동작한다.** 미설정이면 곧바로 폴백(재생 데이터)으로 간다.
  2. **캐시 우선.** SMP는 시간대별 확정값이므로 정시에만 갱신하면 된다.
     수급은 5분 주기. 시연 중 API 호출로 화면이 느려지면 안 된다.
  3. **실패해도 마지막 성공값을 유지한다.** 현장 인터넷이 끊겨도 화면이 비지 않는다.
  4. **출처를 항상 밝힌다.** 화면에 'KPX 실데이터'인지 '재생 데이터'인지 배지로 표시한다.

환경변수:
    KPX_API_KEY   공공데이터포털 일반 인증키(Decoding). 없으면 API 계열 비활성.
    KPX_REGION    jeju | inland  (기본 jeju — 제주 시장 기준 운영)
    KPX_SMP_CSV   SMP CSV 경로 (기본 backend/data/kpx_smp.csv)
"""

from __future__ import annotations

import asyncio
import csv
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)
KST = timezone(timedelta(hours=9))

SUKUB_URL = "https://openapi.kpx.or.kr/openapi/sukub5mToday/getSukub5mToday"
FUEL_URL = "https://openapi.kpx.or.kr/openapi/smpFuelSourceDaily/getSmpFuelSourceDaily"

# CSV 기본 경로 — 공공데이터포털에서 내려받은 '시간별 계통한계가격' 파일
DEFAULT_CSV = Path(__file__).resolve().parents[2] / "data" / "kpx_smp.csv"
# 제주/육지 보정 계수 (scripts/ingest_kpx_smp.py 산출물)
CALIB_JSON = Path(__file__).resolve().parents[2] / "data" / "kpx_calibration.json"

SMP_TTL_S = 600      # 시간별 확정값 — 10분 캐시면 충분
SUKUB_TTL_S = 120    # 5분 주기 데이터
SUKUB_FAIL_BACKOFF_S = 300   # 실패 시 재시도 금지 구간 (무응답 API 태스크 누적 방지)
TIMEOUT_S = 6.0


class KpxFeed:
    def __init__(self) -> None:
        self._smp: list[float] | None = None
        self._smp_at: float = 0.0
        self._sukub: dict[str, Any] | None = None
        self._sukub_at: float = 0.0
        self._fail = 0
        self._last_error: str = ""
        self._calib: dict | None = None
        # 동시 중복 호출 방지 + 실패 백오프
        # (Railway는 해외 IP라 한국 공공 API가 무응답인 경우가 있다. 실패 시각을
        #  기록해두지 않으면 3초 폴링마다 새 HTTP 태스크가 쌓여 서버가 마비된다.)
        self._sukub_inflight: bool = False
        self._sukub_fail_at: float = 0.0

    # ── 상태 ──
    @property
    def enabled(self) -> bool:
        return bool(os.environ.get("KPX_API_KEY", "").strip())

    def status(self) -> dict:
        now = datetime.now(KST)
        return {
            "enabled": self.enabled,
            "smp_cached": self._smp is not None,
            "sukub_cached": self._sukub is not None,
            "smp_age_s": round(now.timestamp() - self._smp_at) if self._smp_at else None,
            "failures": self._fail,
            "last_error": self._last_error,
            "region": os.environ.get("KPX_REGION", "jeju"),
            "csv_path": str(self.csv_path),
            "csv_exists": self.csv_path.exists(),
            "region_scale": self.region_scale(),
            "calibration": (self.calibration() or {}).get("period"),
            "source": "kpx" if self._smp else "replay",
            "label": (
                f"KPX 실데이터 ({'제주' if os.environ.get('KPX_REGION', 'jeju') == 'jeju' else '육지'})"
                if self._smp else "재생 데이터"
            ),
        }

    # ── 수집 ──
    async def _get(self, url: str, extra: dict | None = None) -> Any:
        key = os.environ.get("KPX_API_KEY", "").strip()
        params = {"serviceKey": key, "returnType": "json", **(extra or {})}
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            try:
                return r.json()
            except Exception:  # noqa: BLE001
                # 일부 응답이 XML로 오는 경우가 있어 텍스트를 남겨 진단한다
                raise ValueError(f"JSON 아님: {r.text[:120]}")

    # ── SMP: CSV 파일데이터 (OpenAPI가 행정/공공 전용이라 이 경로를 쓴다) ──
    @property
    def region(self) -> str:
        return os.environ.get("KPX_REGION", "jeju").strip().lower()

    @property
    def csv_path(self) -> Path:
        p = os.environ.get("KPX_SMP_CSV", "").strip()
        return Path(p) if p else DEFAULT_CSV

    def smp_from_csv(self) -> list[float] | None:
        """공공데이터포털 '시간별 계통한계가격' CSV → 24개 곡선.

        컬럼 예: 시간, SMP(육지), SMP(제주)  /  또는 hour, land, jeju
        헤더 이름이 개정되어도 '제주'·'육지' 키워드로 컬럼을 찾는다.
        """
        path = self.csv_path
        if not path.exists():
            return None
        now = datetime.now(KST).timestamp()
        # 파일 수정시각 기준 캐시 (하루 1회 갱신이면 충분)
        if self._smp and (now - self._smp_at) < SMP_TTL_S:
            return self._smp
        try:
            for enc in ("utf-8-sig", "cp949", "utf-8"):
                try:
                    rows = list(csv.DictReader(path.open(encoding=enc)))
                    if rows:
                        break
                except UnicodeDecodeError:
                    continue
            else:
                return None
            if not rows:
                return None

            head = rows[0].keys()
            want = "제주" if self.region == "jeju" else "육지"
            col = next((c for c in head if c and want in c), None)
            if col is None:  # 영문 헤더 대응
                alt = "jeju" if self.region == "jeju" else "land"
                col = next((c for c in head if c and alt in c.lower()), None)
            if col is None:  # 지역 구분이 없는 파일 = 육지 단일
                col = next((c for c in head if c and ("smp" in c.lower() or "가격" in c)), None)
            hcol = next((c for c in head if c and ("시간" in c or c.lower() in ("hour", "hh", "time"))), None)
            if col is None:
                return None

            curve: dict[int, float] = {}
            for i, r in enumerate(rows):
                raw_h = r.get(hcol) if hcol else str(i + 1)
                m = re.search(r"\d+", str(raw_h or ""))
                if not m:
                    continue
                h = int(m.group())
                try:
                    v = float(str(r.get(col, "")).replace(",", "").strip())
                except (TypeError, ValueError):
                    continue
                idx = (h - 1) if h >= 1 and len(rows) >= 24 and max(
                    int(re.search(r"\d+", str(x.get(hcol) or "0")).group())
                    for x in rows if hcol and re.search(r"\d+", str(x.get(hcol) or "0"))
                ) >= 24 else h
                if 0 <= idx <= 23:
                    curve[idx] = v
            if len(curve) < 6:
                return None

            # ── 가짜 데이터 방어 ────────────────────────────────
            # 자리만 채워둔 더미 파일(계단·직선)을 실측으로 오인하면
            # 발표에서 치명적이다. 2차 차분이 0이면 완전한 직선이므로 거부한다.
            # 실제 SMP는 시간마다 변화폭이 제각각이다. 더미는 일정 간격으로
            # 오르내리므로 **1차 차분의 절댓값 종류가 극히 적다**(V자·계단 포함).
            vals = [curve[h] for h in sorted(curve)]
            if len(vals) >= 8:
                steps = {round(abs(b - a), 3) for a, b in zip(vals, vals[1:])}
                steps.discard(0.0)
                if len(steps) <= 2:
                    self._last_error = (
                        f"인위적 패턴 감지(변화폭 {len(steps)}종) — 더미 데이터로 판단해 거부"
                    )
                    logger.warning("kpx_smp_csv_rejected", reason=self._last_error,
                                   file=str(path), steps=sorted(steps)[:5])
                    return None
            out, last = [], next(iter(curve.values()))
            for h in range(24):
                last = curve.get(h, last)
                out.append(round(last, 2))
            self._smp, self._smp_at = out, now
            logger.info("kpx_smp_csv_loaded", region=self.region, file=str(path), sample=out[:3])
            return out
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"CSV 파싱 실패: {exc}"[:160]
            logger.warning("kpx_smp_csv_failed", error=self._last_error)
            return self._smp

    async def smp_today(self) -> list[float] | None:
        """오늘의 시간별 SMP 24개 (CSV 기반). 없으면 None → 호출자가 폴백."""
        return self.smp_from_csv()

    # ── 제주 보정 (월별 실데이터 기반) ──
    def calibration(self) -> dict | None:
        """제주/육지 월별 비율. 시간별 실측이 없을 때 수준 보정에 쓴다."""
        if self._calib is None:
            try:
                import json

                self._calib = json.loads(CALIB_JSON.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                self._calib = {}
        return self._calib or None

    def region_scale(self) -> float:
        """현재 월에 적용할 제주 보정 배수 (육지 기준 곡선 → 제주 수준).

        주의: 최근 데이터에서 제주/육지 비율은 1.0 근처로 수렴했다
        (계통 연계 확충 영향). 과거 평균(1.36)을 그대로 쓰면 과대 추정이 되므로
        **최근 12개월 비율을 기본값**으로 쓰고, 월별 계절성만 상대적으로 반영한다.
        """
        if self.region != "jeju":
            return 1.0
        c = self.calibration()
        if not c:
            return 1.0
        recent = float(c.get("jeju_over_land_recent12", 1.0))
        monthly = c.get("monthly_ratio", {})
        m = str(datetime.now(KST).month)
        all_avg = float(c.get("jeju_over_land_all", 1.0)) or 1.0
        season = float(monthly.get(m, all_avg)) / all_avg   # 계절 상대값만 취한다
        return round(recent * season, 4)

    async def fuel_source(self) -> dict | None:
        """연료원별 SMP 결정횟수 — 제주/육지 구분.

        "오늘 제주 가격을 무엇이 결정했는가"를 보여준다.
        재생에너지 비중이 높은 제주 시장의 특성을 설명하는 근거가 된다.
        """
        if not self.enabled:
            return None
        try:
            data = await self._get(FUEL_URL)
            rows = self._rows(data)
            if not rows:
                return None
            want = "제주" if self.region == "jeju" else "육지"
            counts: dict[str, float] = {}
            for r in rows:
                blob = " ".join(str(v) for v in r.values())
                if want not in blob and self.region == "jeju":
                    continue
                for k, v in r.items():
                    if k and any(t in k for t in ("원자력", "석탄", "LNG", "유류", "신재생", "양수", "기타")):
                        try:
                            counts[k] = counts.get(k, 0.0) + float(str(v).replace(",", ""))
                        except (TypeError, ValueError):
                            continue
            if not counts:
                return None
            top = max(counts, key=counts.get)
            return {"region": self.region, "counts": counts, "top_fuel": top}
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)[:160]
            logger.warning("kpx_fuel_failed", error=self._last_error)
            return None

    async def sukub_now(self) -> dict | None:
        """현재 수급현황 (수요·공급능력·예비력)."""
        if not self.enabled:
            return None
        now = datetime.now(KST).timestamp()
        if self._sukub and (now - self._sukub_at) < SUKUB_TTL_S:
            return self._sukub
        # 직전 실패 후 백오프 구간이면 재시도하지 않는다 (무응답 API에 태스크 누적 방지)
        if (now - self._sukub_fail_at) < SUKUB_FAIL_BACKOFF_S:
            return self._sukub
        # 이미 조회가 진행 중이면 중복 생성하지 않는다
        if self._sukub_inflight:
            return self._sukub
        self._sukub_inflight = True
        try:
            data = await self._get(SUKUB_URL)
            parsed = self._parse_sukub(data)
            if parsed:
                self._sukub, self._sukub_at = parsed, now
                self._sukub_fail_at = 0.0
            else:
                self._sukub_fail_at = now
            return self._sukub
        except Exception as exc:  # noqa: BLE001
            self._fail += 1
            self._sukub_fail_at = now      # 실패도 기록 — 다음 백오프까지 재시도 금지
            self._last_error = str(exc)[:160]
            logger.warning("kpx_sukub_failed", error=self._last_error)
            return self._sukub
        finally:
            self._sukub_inflight = False

    # ── 파싱 ──
    # 공공데이터 응답은 래핑 구조가 제각각이라(items/item, body/items 등)
    # 키 이름으로 재귀 탐색해 안정적으로 뽑는다.
    @staticmethod
    def _rows(payload: Any) -> list[dict]:
        if isinstance(payload, list):
            return [r for r in payload if isinstance(r, dict)]
        if isinstance(payload, dict):
            for k in ("item", "items", "row", "data", "body", "response", "result"):
                if k in payload:
                    got = KpxFeed._rows(payload[k])
                    if got:
                        return got
            # dict 자체가 한 행인 경우
            if any(isinstance(v, (int, float, str)) for v in payload.values()):
                return [payload]
        return []

    @staticmethod
    def _num(row: dict, *names: str) -> float | None:
        for n in names:
            for k, v in row.items():
                if k.lower().replace("_", "") == n.lower().replace("_", ""):
                    try:
                        return float(str(v).replace(",", ""))
                    except (TypeError, ValueError):
                        continue
        return None

    @classmethod
    def _parse_smp(cls, payload: Any) -> list[float] | None:
        """(예비) SMP OpenAPI 응답 파서 — 행정/공공 계정으로 API가 열릴 때를 대비해 유지."""
        rows = cls._rows(payload)
        if not rows:
            return None
        raw: list[tuple[int, float]] = []
        for r in rows:
            h = cls._num(r, "hour", "hh", "tm", "time")
            v = cls._num(r, "smp", "smpValue", "price", "landSmp")
            if h is None or v is None:
                continue
            raw.append((int(h), v))
        if not raw:
            return None

        # 시각 표기가 1~24인지 0~23인지 판별해 맞춘다.
        # (1~24 표기에서 24시는 그날의 마지막 시간 = 인덱스 23)
        hours = [h for h, _ in raw]
        one_based = min(hours) >= 1 and max(hours) >= 24
        curve: dict[int, float] = {}
        for h, v in raw:
            idx = (h - 1) if one_based else h
            if 0 <= idx <= 23:
                curve[idx] = v
        if len(curve) < 6:             # 너무 적으면 파싱 실패로 간주
            return None
        # 빈 시간은 직전 값으로 채운다 (당일 미확정 구간)
        out, last = [], next(iter(curve.values()))
        for h in range(24):
            last = curve.get(h, last)
            out.append(round(last, 2))
        return out

    @classmethod
    def _parse_sukub(cls, payload: Any) -> dict | None:
        rows = cls._rows(payload)
        if not rows:
            return None
        r = rows[-1]                   # 최신 스냅샷
        demand = cls._num(r, "currentPowerTotal", "demand", "load", "curPwrTot")
        supply = cls._num(r, "supplyCapacity", "supply", "supplyAbility")
        reserve = cls._num(r, "supplyReservePower", "reserve", "reservePower")
        rate = cls._num(r, "supplyReserveRate", "reserveRate")
        if demand is None and supply is None:
            return None
        return {
            "demand_mw": demand,
            "supply_mw": supply,
            "reserve_mw": reserve,
            "reserve_rate": rate,
            "ts": datetime.now(KST).strftime("%H:%M:%S"),
        }

    # ── 동기 호출용 헬퍼 (스트림 등 sync 경로에서 사용) ──
    def smp_cached(self) -> list[float] | None:
        """캐시된 값만 즉시 반환. 없으면 None (호출자가 폴백)."""
        return self._smp

    def refresh_background(self) -> None:
        """비차단 갱신 — 응답을 기다리지 않는다. SMP는 CSV라 즉시 읽는다."""
        self.smp_from_csv()
        if not self.enabled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.sukub_now())


kpx_feed = KpxFeed()

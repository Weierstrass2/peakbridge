"""
한전 전력거래소 API 기반 서비스
"""

import time as _time
import xml.etree.ElementTree as ET
from urllib.parse import unquote

import httpx
from datetime import datetime
from typing import Dict
from app.core.config import settings
from app.core.logging import get_logger
from app.services.kpx_feed import KpxFeed


def _now_kst():
    """KST 벽시계 (서버가 UTC여도 한국 시간 기준으로 판정)."""
    from datetime import datetime as _dt, timedelta as _td
    return _dt.utcnow() + _td(hours=9)


logger = get_logger(__name__)

# SMP 인메모리 캐시 (모듈 레벨 — 요청마다 KepcoService가 새로 생겨도 공유됨).
# KPX API가 죽어 있으면 요청당 타임아웃을 그대로 태워 /kepco/status·/ai/scenarios가
# 프론트 axios 타임아웃(10초)을 넘겨버리므로, 성공이든 실패든 결과를 캐시한다.
# value=None 은 "API 전멸" 표시 — TTL 동안 재시도하지 않되, 추정값은 시간대
# 요금이 바뀔 수 있어 캐시하지 않고 매번 새로 계산한다.
_smp_cache: Dict = {"ts": 0.0, "value": None, "live": False}
_SMP_TTL_S = 600
# KPX 호출 요청별 타임아웃. 2개 API 직렬 최악이라도 프론트 10초 안에 끝나야 한다.
_SMP_FETCH_TIMEOUT_S = 3.5


class _LandSmpFeed(KpxFeed):
    """시간별 SMP CSV(backend/data/kpx_smp.csv)를 **육지** 컬럼으로 읽는 리더.

    Railway는 해외 IP라 KPX API 호출이 막힌다 — VPP OS와 동일하게
    PC에서 내려받은 공공데이터포털 파일데이터를 서버가 읽는 우회를 쓴다.
    VPP 시장(kpx_feed 싱글톤, KPX_REGION 기본 jeju)과 캐시를 섞지 않도록
    별도 인스턴스 + 육지 고정. 파서·더미 데이터 방어는 그대로 상속.
    """

    @property
    def region(self) -> str:  # noqa: D102 — env 무시, 아파트 관제는 육지 기준
        return "inland"


_land_smp_feed = _LandSmpFeed()


class KepcoService:
    """한전 API 연동 서비스"""
    
    def __init__(self):
        # data.go.kr 서비스키는 인코딩/디코딩 두 버전이 발급되는데, 인코딩 버전을
        # 그대로 params에 넣으면 httpx가 한 번 더 인코딩해 인증이 깨진다.
        # '%'가 들어 있으면 인코딩 버전으로 보고 디코딩해 저장한다.
        raw_key = settings.KEPCO_API_KEY or ""
        self.api_key = unquote(raw_key) if "%" in raw_key else raw_key
        self.client = httpx.AsyncClient(timeout=10.0)
    
    # 계절별 요금 (원/kWh) — EnergyOptimizer.RATES와 동일 기준.
    # 여기가 어긋나면 SMP 폴백 추정과 "현재 요금" KPI가 서로 모순된 값을 보인다.
    SEASON_TARIFFS = {
        "여름": {"경부하": 42.5, "중간부하": 84.5, "최대부하": 147.0},
        "봄가을": {"경부하": 42.5, "중간부하": 62.9, "최대부하": 85.6},
        "겨울": {"경부하": 42.5, "중간부하": 78.8, "최대부하": 107.2},
    }

    def get_current_tariff_info(self) -> tuple:
        """현재 시간대 요금 정보 반환"""
        now = _now_kst()
        hour = now.hour
        month = now.month

        # 계절 구분 (기존 `11 <= month <= 2`는 항상 거짓 — 겨울이 봄가을로 새던 버그)
        if 7 <= month <= 8:
            season = "여름"
        elif month >= 11 or month <= 2:
            season = "겨울"
        else:
            season = "봄가을"

        # 시간대 구분
        if 23 <= hour or hour < 9:
            period = "경부하"
        elif (9 <= hour < 11) or (13 <= hour < 17) or (21 <= hour < 23):
            period = "중간부하"
        else:
            period = "최대부하"

        return period, self.SEASON_TARIFFS[season][period]
    
    def estimate_smp_from_tariff(self) -> float:
        """요금 기반 SMP 추정 (폴백)"""
        _, tariff = self.get_current_tariff_info()
        return tariff * 1.0
    
    def _has_valid_key(self) -> bool:
        """서비스키가 실질적으로 설정돼 있는지 (빈값·플레이스홀더 조기 차단)."""
        k = (self.api_key or "").strip()
        return len(k) >= 20 and "여기에" not in k and k.lower() not in ("none", "changeme")

    def _smp_from_csv(self) -> float | None:
        """시간별 SMP CSV(육지)에서 현재 시각 값. 파일 없으면 None."""
        curve = _land_smp_feed.smp_from_csv()
        if not curve:
            return None
        return curve[_now_kst().hour]

    def _smp_from_inject(self) -> float | None:
        """로컬 중계(hardware/server smp_relay 또는 fetch_smp_local)가
        /market/smp-api/inject 로 주입한 **당일** 육지 곡선에서 현재 시각 값."""
        try:
            from app.services.kpx_smp_api import smp_api

            curve = smp_api.smp_land_today()
            if curve:
                return curve[_now_kst().hour]
        except Exception as e:  # noqa: BLE001
            logger.warning("smp_inject_read_failed", error=str(e))
        return None

    async def get_smp_info(self) -> tuple[float, str]:
        """(SMP 원/kWh, 출처) 반환. 출처: "api" | "inject" | "csv" | "estimate".

        전날 KPX가 결정한 실제 시간별 SMP를 두 공공데이터 API로 시도한다.
          1) getSmp1hToday — 육지 계통한계가격 시간별(스펙 명확, XML)
          2) SmpWithForecastDemand — 계통한계가격+수요예측(신규 권장, JSON)
        API 실패 시(Railway는 해외 IP라 한국 공공 API가 막힌다) 폴백 순서:
          로컬 중계가 주입한 **당일** 곡선(inject) → 커밋해 둔 시간별 SMP
          CSV(실데이터, 갱신일 기준) → 요금표 추정.
        API 결과는 10분 캐시하고 실패도 캐시해 응답을 지연시키지 않는다.
        """
        if self._has_valid_key():
            cached_age = _time.time() - _smp_cache["ts"]
            if cached_age < _SMP_TTL_S:
                if _smp_cache["value"] is not None:
                    return _smp_cache["value"], "api"
                # TTL 내 "API 전멸" 기록 — 재시도 없이 CSV/추정으로
            else:
                hour = _now_kst().hour
                smp = await self._fetch_smp1h_today(hour)
                if smp is None:
                    smp = await self._fetch_smp_forecast(hour)
                if smp is not None:
                    _smp_cache.update(ts=_time.time(), value=smp, live=True)
                    return smp, "api"
                logger.warning("smp_all_apis_failed_trying_csv_fallback")
                _smp_cache.update(ts=_time.time(), value=None, live=False)
        else:
            logger.info("smp_no_api_key_trying_csv_fallback")

        injected = self._smp_from_inject()
        if injected is not None:
            return injected, "inject"
        csv_smp = self._smp_from_csv()
        if csv_smp is not None:
            return csv_smp, "csv"
        return self.estimate_smp_from_tariff(), "estimate"

    async def get_current_smp(self) -> float:
        """현재 SMP 가격만 필요할 때 (원/kWh). 캐시 포함 — get_smp_info 참조."""
        smp, _ = await self.get_smp_info()
        return smp

    async def _fetch_smp1h_today(self, hour: int) -> float | None:
        """getSmp1hToday (XML). 응답 item들에서 tradHour == 현재시각의 smp를 찾는다."""
        try:
            url = "https://openapi.kpx.or.kr/openapi/smp1hToday/getSmp1hToday"
            params = {"ServiceKey": self.api_key, "areaCd": 1}
            resp = await self.client.get(url, params=params, timeout=_SMP_FETCH_TIMEOUT_S)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            latest = None
            for item in root.iter("item"):
                h_el = item.find("tradHour")
                s_el = item.find("smp")
                if s_el is None or s_el.text is None:
                    continue
                smp_val = float(s_el.text)
                latest = smp_val  # 마지막 유효값 보관(현재시각 미매칭 시 폴백)
                if h_el is not None and h_el.text is not None and int(h_el.text) == hour:
                    return smp_val
            return latest  # 정확한 시각이 없으면 가장 최근 값
        except Exception as e:  # noqa: BLE001
            logger.warning("smp1h_today_failed", error=str(e))
            return None

    async def _fetch_smp_forecast(self, hour: int) -> float | None:
        """SmpWithForecastDemand (JSON). item들에서 현재시각 smp를 찾는다."""
        try:
            today = _now_kst().strftime("%Y%m%d")
            url = "https://apis.data.go.kr/B552115/SmpWithForecastDemand"
            params = {
                "serviceKey": self.api_key,
                "pageNo": 1,
                "numOfRows": 25,
                "dataType": "json",
                "areaCd": 1,
                "yymmdd": today,
            }
            resp = await self.client.get(url, params=params, timeout=_SMP_FETCH_TIMEOUT_S)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            if isinstance(items, dict):
                items = [items]
            latest = None
            for item in items:
                smp_raw = item.get("smp")
                if smp_raw is None:
                    continue
                latest = float(smp_raw)
                # 시각 필드명이 API 버전별로 다를 수 있어 여러 후보를 본다
                h = item.get("hour", item.get("tradHour", item.get("tradeHour")))
                if h is not None and int(h) == hour:
                    return float(smp_raw)
            return latest
        except Exception as e:  # noqa: BLE001
            logger.warning("smp_forecast_failed", error=str(e))
            return None
    
    async def get_power_reserve(self) -> float:
        """현재 전력 예비율 반환 (%)"""
        try:
            # 예비율 API는 별도로 추후 추가. 현재는 기본값 반환
            return 15.0
        except Exception as e:
            logger.warning("get_power_reserve_failed", error=str(e))
            return 15.0
    
    async def is_power_emergency(self) -> bool:
        """전력 비상 여부 (예비율 10% 이하)"""
        reserve = await self.get_power_reserve()
        return reserve < 10.0
    
    async def get_state_data(self) -> Dict:
        """RL 상태 수집용 메서드"""
        smp = await self.get_current_smp()
        reserve = await self.get_power_reserve()
        is_emergency = await self.is_power_emergency()
        
        return {
            "smp_price": smp,
            "power_reserve": reserve,
            "is_emergency": is_emergency
        }
    
    async def get_kepco_summary(self) -> Dict:
        """대시보드용 전체 요약"""
        smp, smp_source = await self.get_smp_info()
        reserve = await self.get_power_reserve()
        is_emergency = await self.is_power_emergency()
        period, tariff = self.get_current_tariff_info()

        source_label = {
            "api": "한전 공공데이터 API (실시간 SMP)",
            "inject": "KPX 하루전 확정가 (당일 — 로컬 중계 자동 주입)",
            "csv": "KPX 시간별 SMP 실데이터 (파일데이터 — 전일 확정가)",
            "estimate": "요금표 기반 추정 (SMP 실데이터 미연동 — kpx_smp.csv 배치 시 실데이터)",
        }[smp_source]
        return {
            "smp_price": smp,
            # 실데이터 여부 — API든 CSV든 KPX가 결정한 실제 가격이면 true
            "smp_is_live": smp_source != "estimate",
            "smp_source": smp_source,
            "power_reserve": reserve,
            "is_emergency": is_emergency,
            "current_tariff": tariff,
            "tariff_period": period,
            "source": source_label,
        }

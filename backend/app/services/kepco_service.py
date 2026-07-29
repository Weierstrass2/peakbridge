"""
한전 전력거래소 API 기반 서비스
"""

import xml.etree.ElementTree as ET

import httpx
from datetime import datetime
from typing import Dict
from app.core.config import settings
from app.core.logging import get_logger


def _now_kst():
    """KST 벽시계 (서버가 UTC여도 한국 시간 기준으로 판정)."""
    from datetime import datetime as _dt, timedelta as _td
    return _dt.utcnow() + _td(hours=9)


logger = get_logger(__name__)


class KepcoService:
    """한전 API 연동 서비스"""
    
    def __init__(self):
        self.api_key = settings.KEPCO_API_KEY
        self.client = httpx.AsyncClient(timeout=10.0)
    
    def get_current_tariff_info(self) -> tuple:
        """현재 시간대 요금 정보 반환"""
        now = _now_kst()
        hour = now.hour
        month = now.month
        
        # 계절 구분
        if 7 <= month <= 8:
            season = "여름"
        elif 11 <= month <= 2:
            season = "겨울"
        else:
            season = "봄가을"
        
        # 시간대 구분
        if 23 <= hour or hour < 9:
            period = "경부하"
            tariff = 42.5
        elif (9 <= hour < 11) or (13 <= hour < 17) or (21 <= hour < 23):
            period = "중간부하"
            tariff = 84.5
        else:
            period = "최대부하"
            tariff = 147.0
        
        return period, tariff
    
    def estimate_smp_from_tariff(self) -> float:
        """요금 기반 SMP 추정 (폴백)"""
        _, tariff = self.get_current_tariff_info()
        return tariff * 1.0
    
    def _has_valid_key(self) -> bool:
        """서비스키가 실질적으로 설정돼 있는지 (빈값·플레이스홀더 조기 차단)."""
        k = (self.api_key or "").strip()
        return len(k) >= 20 and "여기에" not in k and k.lower() not in ("none", "changeme")

    async def get_current_smp(self) -> float:
        """현재 SMP 가격 반환 (원/kWh).

        전날 KPX가 결정한 실제 시간별 SMP를 두 공공데이터 API로 시도한다.
          1) getSmp1hToday — 육지 계통한계가격 시간별(스펙 명확, XML)
          2) SmpWithForecastDemand — 계통한계가격+수요예측(신규 권장, JSON)
        키가 없거나 둘 다 실패하면 요금표 기반 추정으로 폴백한다.
        """
        if not self._has_valid_key():
            logger.info("smp_no_api_key_using_tariff_fallback")
            return self.estimate_smp_from_tariff()

        hour = _now_kst().hour
        smp = await self._fetch_smp1h_today(hour)
        if smp is not None:
            return smp
        smp = await self._fetch_smp_forecast(hour)
        if smp is not None:
            return smp

        logger.warning("smp_all_apis_failed_using_tariff_fallback")
        return self.estimate_smp_from_tariff()

    async def _fetch_smp1h_today(self, hour: int) -> float | None:
        """getSmp1hToday (XML). 응답 item들에서 tradHour == 현재시각의 smp를 찾는다."""
        try:
            url = "https://openapi.kpx.or.kr/openapi/smp1hToday/getSmp1hToday"
            params = {"ServiceKey": self.api_key, "areaCd": 1}
            resp = await self.client.get(url, params=params)
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
            resp = await self.client.get(url, params=params)
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
        smp = await self.get_current_smp()
        reserve = await self.get_power_reserve()
        is_emergency = await self.is_power_emergency()
        period, tariff = self.get_current_tariff_info()

        # SMP가 요금표 값과 정확히 같으면 폴백 중(실 API 미연동) — 화면에서 정직하게 구분
        is_fallback = abs(smp - tariff) < 0.01
        return {
            "smp_price": smp,
            "smp_is_live": not is_fallback,
            "power_reserve": reserve,
            "is_emergency": is_emergency,
            "current_tariff": tariff,
            "tariff_period": period,
            "source": "한전 공공데이터 API (실시간 SMP)" if not is_fallback
            else "요금표 기반 추정 (SMP API 미연동 — KEPCO_API_KEY 설정 시 실 SMP 연동)",
        }

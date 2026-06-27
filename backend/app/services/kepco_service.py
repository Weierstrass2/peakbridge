"""
한전 전력거래소 API 기반 서비스
"""

import httpx
from datetime import datetime
from typing import Dict
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class KepcoService:
    """한전 API 연동 서비스"""
    
    def __init__(self):
        self.api_key = settings.KEPCO_API_KEY or "bfd9f8210ee4ea52b156c2b570822168f22977469c8765f7c346e217edc97533"
        self.client = httpx.AsyncClient(timeout=10.0)
    
    def _get_current_tariff_info(self) -> tuple:
        """현재 시간대 요금 정보 반환"""
        now = datetime.now()
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
        _, tariff = self._get_current_tariff_info()
        return tariff * 1.0
    
    async def get_current_smp(self) -> float:
        """현재 SMP 가격 반환 (원/kWh)"""
        try:
            today = datetime.now().strftime("%Y%m%d")
            current_hour = datetime.now().hour
            
            url = "https://apis.data.go.kr/B552115/SmpWithForecastDemand"
            params = {
                "serviceKey": self.api_key,
                "pageNo": 1,
                "numOfRows": 25,
                "dataType": "json",
                "areaCd": 1,
                "yymmdd": today
            }
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            
            for item in items:
                item_hour = int(item.get("hour", 0))
                if item_hour == current_hour:
                    return float(item.get("smp", 0))
            
            return self.estimate_smp_from_tariff()
        except Exception as e:
            logger.warning("get_current_smp_failed", error=str(e))
            return self.estimate_smp_from_tariff()
    
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
        period, tariff = self._get_current_tariff_info()
        
        return {
            "smp_price": smp,
            "power_reserve": reserve,
            "is_emergency": is_emergency,
            "current_tariff": tariff,
            "tariff_period": period,
            "source": "한전 공공데이터 API"
        }

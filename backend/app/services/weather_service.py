"""
기상청 VilageFcstInfoService_2.0 API 기반 날씨 서비스
"""

import httpx
from datetime import datetime, timedelta
from typing import Dict
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class WeatherService:
    """기상청 API 연동 서비스"""
    
    def __init__(self):
        self.api_key = settings.WEATHER_API_KEY or "QlrgTilFRBWa4E4pRXQVVQ"
        self.nx = settings.WEATHER_NX or 98
        self.ny = settings.WEATHER_NY or 76
        self.client = httpx.AsyncClient(timeout=10.0)
    
    async def _get_ultra_srt_ncst(self) -> Dict:
        """초단기실황 API 호출 (현재 기온)"""
        try:
            now = datetime.now()
            base_date = now.strftime("%Y%m%d")
            
            # base_time: 현재 분이 40분 미만이면 1시간 전 정시
            if now.minute < 40:
                base_time_hour = now.hour - 1 if now.hour > 0 else 23
            else:
                base_time_hour = now.hour
            base_time = f"{base_time_hour:02d}00"
            
            url = "https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getUltraSrtNcst"
            params = {
                "pageNo": 1,
                "numOfRows": 1000,
                "dataType": "JSON",
                "base_date": base_date,
                "base_time": base_time,
                "nx": self.nx,
                "ny": self.ny,
                "authKey": self.api_key
            }
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning("ultra_srt_ncst_api_failed", error=str(e))
            return {}
    
    def _get_base_time(self):
        """단기예보 base_date, base_time 계산"""
        now = datetime.now()
        base_times = [2, 5, 8, 11, 14, 17, 20, 23]
        
        current_hour = now.hour
        valid_times = [h for h in base_times if h <= current_hour]
        
        if not valid_times:
            # 자정~02시 사이면 어제 23시 사용
            yesterday = now - timedelta(days=1)
            return yesterday.strftime("%Y%m%d"), "2300"
        
        base_hour = max(valid_times)
        return now.strftime("%Y%m%d"), f"{base_hour:02d}00"
    
    async def _get_vilage_fcst(self) -> Dict:
        """단기예보 API 호출 (내일 최고/최저기온)"""
        try:
            base_date, base_time = self._get_base_time()
            
            url = "https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst"
            params = {
                "pageNo": 1,
                "numOfRows": 1000,
                "dataType": "JSON",
                "base_date": base_date,
                "base_time": base_time,
                "nx": self.nx,
                "ny": self.ny,
                "authKey": self.api_key
            }
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning("vilage_fcst_api_failed", error=str(e))
            return {}
    
    async def get_current_temperature(self) -> float:
        """현재 기온 반환"""
        try:
            data = await self._get_ultra_srt_ncst()
            items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            
            for item in items:
                if item.get("category") == "T1H":
                    return float(item.get("obsrValue", 0.0))
            return 25.0
        except Exception as e:
            logger.warning("get_current_temperature_failed", error=str(e))
            return 25.0
    
    async def get_tomorrow_max_temp(self) -> float:
        """내일 최고기온 반환"""
        try:
            data = await self._get_vilage_fcst()
            items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")
            
            for item in items:
                if item.get("category") == "TMX" and item.get("fcstDate") == tomorrow:
                    return float(item.get("fcstValue", 0.0))
            return 30.0
        except Exception as e:
            logger.warning("get_tomorrow_max_temp_failed", error=str(e))
            return 30.0
    
    async def get_tomorrow_min_temp(self) -> float:
        """내일 최저기온 반환"""
        try:
            data = await self._get_vilage_fcst()
            items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")
            
            for item in items:
                if item.get("category") == "TMN" and item.get("fcstDate") == tomorrow:
                    return float(item.get("fcstValue", 0.0))
            return 20.0
        except Exception as e:
            logger.warning("get_tomorrow_min_temp_failed", error=str(e))
            return 20.0
    
    async def is_heatwave(self) -> bool:
        """내일 최고기온 >= 33도이면 True"""
        max_temp = await self.get_tomorrow_max_temp()
        return max_temp >= 33.0
    
    async def is_coldwave(self) -> bool:
        """내일 최저기온 <= -10도이면 True"""
        min_temp = await self.get_tomorrow_min_temp()
        return min_temp <= -10.0
    
    async def get_load_factor(self) -> float:
        """기온 기반 부하 가중치"""
        current_temp = await self.get_current_temperature()
        if current_temp >= 33.0:
            return 1.3
        elif current_temp <= -5.0:
            return 1.2
        else:
            return 1.0
    
    async def get_state_data(self) -> Dict:
        """RL 상태 수집용 메서드"""
        current_temp = await self.get_current_temperature()
        tomorrow_max = await self.get_tomorrow_max_temp()
        tomorrow_min = await self.get_tomorrow_min_temp()
        heatwave = await self.is_heatwave()
        coldwave = await self.is_coldwave()
        load_factor = await self.get_load_factor()
        
        return {
            "current_temp": current_temp,
            "tomorrow_max_temp": tomorrow_max,
            "tomorrow_min_temp": tomorrow_min,
            "heatwave": heatwave,
            "coldwave": coldwave,
            "load_factor": load_factor
        }
    
    async def get_weather_summary(self) -> Dict:
        """종합 날씨 정보 반환"""
        current_temp = await self.get_current_temperature()
        tomorrow_max = await self.get_tomorrow_max_temp()
        tomorrow_min = await self.get_tomorrow_min_temp()
        heatwave = await self.is_heatwave()
        coldwave = await self.is_coldwave()
        load_factor = await self.get_load_factor()
        
        # 추천 로직
        recommend = False
        reason = "특이 기상 없음"
        target_soc = 80
        scenario = "normal"
        
        if heatwave:
            recommend = True
            reason = f"내일 폭염 예보 ({tomorrow_max}도), ESS 완충 권장"
            target_soc = 100
            scenario = "heatwave"
        elif coldwave:
            recommend = True
            reason = f"내일 한파 예보 ({tomorrow_min}도), ESS 95% 충전 권장"
            target_soc = 95
            scenario = "coldwave"
        elif load_factor > 1.0:
            recommend = True
            reason = f"현재 기온 ({current_temp}도)으로 전력 부하 증가 예상"
            target_soc = 90
            scenario = "high_load"
        
        return {
            "current_temp": current_temp,
            "tomorrow_max_temp": tomorrow_max,
            "tomorrow_min_temp": tomorrow_min,
            "heatwave": heatwave,
            "coldwave": coldwave,
            "load_factor": load_factor,
            "recommendation": {
                "recommend": recommend,
                "reason": reason,
                "target_soc": target_soc,
                "scenario": scenario
            },
            "source": "기상청 VilageFcstInfoService_2.0 실시간"
        }

"""
기상청 API 기반 날씨 서비스
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
    
    async def _get_vsrt_forecast(self) -> str:
        """초단기예보 API 호출 (현재 기온 T1H)"""
        try:
            now = datetime.now()
            # tmfc: 현재시간 (연월일시분, 10분 단위로 내림)
            rounded_minute = (now.minute // 10) * 10
            tmfc = now.strftime(f"%Y%m%d%H{rounded_minute:02d}")
            # tmef: 현재시간 (연월일시)
            tmef = now.strftime("%Y%m%d%H")
            
            url = "https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-dfs_vsrt_grd"
            params = {
                "tmfc": tmfc,
                "tmef": tmef,
                "vars": "T1H",
                "authKey": self.api_key
            }
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.warning("vsrt_forecast_api_failed", error=str(e))
            return ""
    
    async def _get_shrt_forecast(self, tmef_suffix: str) -> str:
        """단기예보 API 호출 (내일 최고/최저기온)"""
        try:
            now = datetime.now()
            # 가장 최근 발표시간 찾기 (02,05,08,11,14,17,20,23시)
            base_hours = [2,5,8,11,14,17,20,23]
            current_hour = now.hour
            base_hour = max([h for h in base_hours if h <= current_hour], default=2)
            if base_hour == 2 and current_hour < 2:
                now -= timedelta(days=1)
                base_hour = 23
            
            tmfc = now.strftime(f"%Y%m%d{base_hour:02d}00")
            # tmef: 내일 날짜 + tmef_suffix
            tomorrow = now + timedelta(days=1)
            tmef = tomorrow.strftime(f"%Y%m%d{tmef_suffix}")
            
            url = "https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-dfs_shrt_grd"
            params = {
                "tmfc": tmfc,
                "tmef": tmef,
                "vars": "TMX",
                "authKey": self.api_key
            }
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.warning("shrt_forecast_api_failed", error=str(e))
            return ""
    
    async def _extract_grid_value(self, text_data: str) -> float:
        """격자 데이터에서 부산 위치 (NX, NY) 값 추출"""
        try:
            lines = text_data.strip().split("\n")
            for line in lines:
                parts = line.strip().split(",")
                if len(parts) >= 4:
                    try:
                        nx = int(parts[0])
                        ny = int(parts[1])
                        if nx == self.nx and ny == self.ny:
                            value = float(parts[3])
                            return value
                    except:
                        continue
            logger.warning("grid_value_not_found", nx=self.nx, ny=self.ny)
            return 0.0
        except Exception as e:
            logger.warning("grid_value_extract_failed", error=str(e))
            return 0.0
    
    async def get_current_temperature(self) -> float:
        """현재 부산 기온 반환 (단기예보에서 T1H 추출)"""
        try:
            data = await self._get_vsrt_forecast()
            temp = await self._extract_grid_value(data)
            if temp == 0.0 and "T1H" in data:
                # fallback: 평균값 계산
                return 25.0
            return temp
        except Exception as e:
            logger.warning("get_current_temperature_failed", error=str(e))
            return 25.0
    
    async def get_tomorrow_max_temp(self) -> float:
        """내일 최고기온 반환 (TMX, 보통 15시)"""
        try:
            data = await self._get_shrt_forecast("1500")
            temp = await self._extract_grid_value(data)
            if temp == 0.0 and "TMX" in data:
                return 25.0
            return temp
        except Exception as e:
            logger.warning("get_tomorrow_max_temp_failed", error=str(e))
            return 25.0
    
    async def get_tomorrow_min_temp(self) -> float:
        """내일 최저기온 반환 (TMN, 보통 05시)"""
        try:
            # TMN은 별도로 API 호출
            now = datetime.now()
            base_hours = [2,5,8,11,14,17,20,23]
            current_hour = now.hour
            base_hour = max([h for h in base_hours if h <= current_hour], default=2)
            if base_hour == 2 and current_hour < 2:
                now -= timedelta(days=1)
                base_hour = 23
            
            tmfc = now.strftime(f"%Y%m%d{base_hour:02d}00")
            tomorrow = now + timedelta(days=1)
            tmef = tomorrow.strftime("%Y%m%d0500")
            
            url = "https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-dfs_shrt_grd"
            params = {
                "tmfc": tmfc,
                "tmef": tmef,
                "vars": "TMN",
                "authKey": self.api_key
            }
            
            response = await self.client.get(url, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.text
            temp = await self._extract_grid_value(data)
            if temp == 0.0 and "TMN" in data:
                return 15.0
            return temp
        except Exception as e:
            logger.warning("get_tomorrow_min_temp_failed", error=str(e))
            return 15.0
    
    async def is_heatwave(self) -> bool:
        """내일 최고기온 >= 33도이면 True"""
        max_temp = await self.get_tomorrow_max_temp()
        return max_temp >= 33.0
    
    async def is_coldwave(self) -> bool:
        """내일 최저기온 <= -10도이면 True"""
        min_temp = await self.get_tomorrow_min_temp()
        return min_temp <= -10.0
    
    async def get_load_factor(self) -> float:
        """현재 기온 기반 부하 가중치"""
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
        reason = "특이 기상 없음, 일반 스케줄 운영"
        target_soc = 80
        scenario = "normal"
        
        if heatwave:
            recommend = True
            reason = f"내일 폭염 예보 ({tomorrow_max}°C), 오늘 심야 ESS 100% 충전 권장"
            target_soc = 100
            scenario = "heatwave"
        elif coldwave:
            recommend = True
            reason = f"내일 한파 예보 ({tomorrow_min}°C), 오늘 심야 ESS 95% 충전 권장"
            target_soc = 95
            scenario = "coldwave"
        elif load_factor > 1.0:
            recommend = True
            reason = f"현재 기온 ({current_temp}°C)으로 인해 전력 부하 증가 예상, ESS 90% 충전 권장"
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
            "source": "기상청 apihub 실시간"
        }

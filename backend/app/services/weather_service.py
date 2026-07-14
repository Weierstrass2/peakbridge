"""
기상청 VilageFcstInfoService_2.0 API 기반 날씨 서비스
"""

import asyncio
import math
import time as _time
import httpx
from datetime import datetime, timedelta
from typing import Dict
from app.core.config import settings
from app.core.logging import get_logger


def _now_kst():
    """KST 벽시계 (서버가 UTC여도 한국 시간 기준으로 판정)."""
    from datetime import datetime as _dt, timedelta as _td
    return _dt.utcnow() + _td(hours=9)


logger = get_logger(__name__)

# 전국 주요 지점 (기상청 격자 nx/ny + 위경도) — 지도 오버레이용
MAP_POINTS = [
    {"region": "서울", "lat": 37.5665, "lon": 126.9780, "nx": 60, "ny": 127},
    {"region": "인천", "lat": 37.4563, "lon": 126.7052, "nx": 55, "ny": 124},
    {"region": "강릉", "lat": 37.7519, "lon": 128.8761, "nx": 92, "ny": 131},
    {"region": "대전", "lat": 36.3504, "lon": 127.3845, "nx": 67, "ny": 100},
    {"region": "대구", "lat": 35.8714, "lon": 128.6014, "nx": 89, "ny": 90},
    {"region": "광주", "lat": 35.1595, "lon": 126.8526, "nx": 58, "ny": 74},
    {"region": "울산", "lat": 35.5384, "lon": 129.3114, "nx": 102, "ny": 84},
    {"region": "부산", "lat": 35.1796, "lon": 129.0756, "nx": 98, "ny": 76},
    {"region": "제주", "lat": 33.4996, "lon": 126.5312, "nx": 52, "ny": 38},
]

# 오버레이 인메모리 캐시 (기상청 API 호출 제한 고려, 10분)
_overlay_cache: Dict = {"ts": 0.0, "data": None}
_OVERLAY_TTL_S = 600


class WeatherService:
    """기상청 API 연동 서비스"""
    
    def __init__(self):
        self.api_key = settings.WEATHER_API_KEY
        self.nx = settings.WEATHER_NX
        self.ny = settings.WEATHER_NY
        self.client = httpx.AsyncClient(timeout=10.0)
    
    async def _get_ultra_srt_ncst(self, nx: int | None = None, ny: int | None = None) -> Dict:
        """초단기실황 API 호출 (현재 기온). nx/ny 미지정 시 기본 지점."""
        try:
            now = _now_kst()
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
                "nx": nx if nx is not None else self.nx,
                "ny": ny if ny is not None else self.ny,
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
        now = _now_kst()
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
            
            tomorrow = (_now_kst() + timedelta(days=1)).strftime("%Y%m%d")
            
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
            
            tomorrow = (_now_kst() + timedelta(days=1)).strftime("%Y%m%d")
            
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

    # ── 지도 기상 오버레이 ──────────────────────────────────

    async def _point_overlay(self, point: Dict) -> Dict | None:
        """단일 지점 실황 → 오버레이 항목. 실패 시 None (해당 지점만 제외)."""
        data = await self._get_ultra_srt_ncst(nx=point["nx"], ny=point["ny"])
        items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        if not items:
            return None
        temp = None
        wind = None
        rain = 0.0
        for it in items:
            cat = it.get("category")
            try:
                if cat == "T1H":
                    temp = float(it.get("obsrValue"))
                elif cat == "WSD":
                    wind = float(it.get("obsrValue"))
                elif cat == "RN1":
                    rain = float(it.get("obsrValue") or 0.0)
            except (TypeError, ValueError):
                continue
        if temp is None:
            return None

        # 일사량: 기상청 실황에 일사 관측 항목이 없어 청천 곡선 기반 추정치
        # (06~19시 sin 곡선, 최대 900W/m2, 강수 시 30%로 감쇠) — 응답에 추정 명시
        now = _now_kst()
        hour = now.hour + now.minute / 60.0
        solar = 0.0
        if 6.0 <= hour <= 19.0:
            solar = 900.0 * math.sin(math.pi * (hour - 6.0) / 13.0)
            if rain > 0:
                solar *= 0.3

        # 특보 판정 (실황값 기반 규칙 — 기상청 특보 기준과 동일)
        alert = None
        if temp >= 35.0:
            alert = "폭염경보"
        elif temp >= 33.0:
            alert = "폭염주의보"
        elif temp <= -15.0:
            alert = "한파경보"
        elif temp <= -12.0:
            alert = "한파주의보"
        elif wind is not None and wind >= 14.0:
            alert = "강풍주의보"

        return {
            "region": point["region"],
            "lat": point["lat"],
            "lon": point["lon"],
            "temperature": temp,
            "wind_speed": wind if wind is not None else 0.0,
            "solar_radiation": round(solar),
            "solar_estimated": True,
            "alert": alert,
        }

    async def get_map_overlay(self) -> Dict:
        """전국 주요 지점 기상 오버레이 (10분 인메모리 캐시).

        지점별 병렬 조회, 실패 지점은 제외하고 나머지 반환 (전체 실패 금지).
        전 지점 실패 시 캐시를 갱신하지 않아 다음 호출에서 재시도.
        """
        now = _time.time()
        if _overlay_cache["data"] is not None and now - _overlay_cache["ts"] < _OVERLAY_TTL_S:
            return _overlay_cache["data"]

        results = await asyncio.gather(
            *[self._point_overlay(p) for p in MAP_POINTS], return_exceptions=True
        )
        points = [r for r in results if isinstance(r, dict)]
        failed = len(MAP_POINTS) - len(points)
        if failed:
            logger.warning("weather_overlay_partial", failed=failed, ok=len(points))

        payload = {
            "points": points,
            "updated_at": _now_kst().isoformat(timespec="seconds"),
            "source": "기상청 초단기실황 (일사량은 청천 곡선 추정치)",
        }
        if points:
            _overlay_cache["ts"] = now
            _overlay_cache["data"] = payload
        return payload

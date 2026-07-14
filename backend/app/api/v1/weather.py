"""
날씨 API 라우터
"""

from fastapi import APIRouter
from typing import Dict
from app.services.weather_service import WeatherService

router = APIRouter()
weather_service = WeatherService()


@router.get("/current", response_model=Dict)
async def get_current_weather():
    """현재 날씨 정보 반환"""
    return await weather_service.get_weather_summary()


@router.get("/state", response_model=Dict)
async def get_weather_state():
    """RL 에이전트용 상태 데이터 반환"""
    return await weather_service.get_state_data()


@router.get("/map-overlay", response_model=Dict)
async def get_map_overlay():
    """전국 주요 지점 기상 오버레이 (지도용, 10분 캐시)"""
    return await weather_service.get_map_overlay()

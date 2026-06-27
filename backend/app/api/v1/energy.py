"""
에너지 최적화 API 라우터
"""

from fastapi import APIRouter, Depends
from datetime import datetime
from typing import Dict, List
from app.ml.energy_optimizer import EnergyOptimizer
from app.db.base import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.device_repository import DeviceRepository
from app.repositories.sensor_repository import SensorRepository

router = APIRouter()
optimizer = EnergyOptimizer()


@router.get("/current-rate", response_model=Dict)
async def get_current_rate():
    """현재 실제 적용 요금 반환"""
    return optimizer.get_current_rate()


@router.get("/schedule/{building_id}", response_model=Dict)
async def get_24h_schedule(
    building_id: str,
    db: AsyncSession = Depends(get_db)
):
    """오늘 최적 충방전 스케줄"""
    device_repo = DeviceRepository(db)
    sensor_repo = SensorRepository(db)
    
    # ESS 디바이스 조회
    devices = await device_repo.list_by_building(building_id)
    ess_device = next((d for d in devices if d.device_type == "ess"), None)

    # 현재 ESS 상태 조회
    ess_soc = 50.0
    ess_capacity = 100.0  # 기본값
    if ess_device:
        soc_reading = await sensor_repo.get_latest(ess_device.device_id, "ess_soc")
        if soc_reading:
            ess_soc = soc_reading.value

    # 간단한 forecast (실제로는 forecast 서비스에서 가져옴)
    forecast = []
    schedule_result = optimizer.calculate_optimal_schedule(ess_soc, ess_capacity, forecast)

    return {
        "building_id": building_id,
        "schedule": schedule_result["schedule"],
        "expected_savings": schedule_result["expected_savings"],
        "expected_arbitrage": schedule_result["expected_arbitrage"]
    }


@router.get("/arbitrage/{building_id}", response_model=Dict)
async def get_arbitrage(
    building_id: str,
    db: AsyncSession = Depends(get_db)
):
    """오늘 실제 차익 계산"""
    # 간단한 예시 계산
    season = optimizer._get_season(datetime.now())
    arbitrage = optimizer.calculate_arbitrage(
        charged_kwh=5.0,
        discharged_kwh=4.5,
        charge_period="경부하",
        discharge_period="최대부하",
        season=season
    )

    return {
        "building_id": building_id,
        "date": datetime.now().strftime("%Y-%m-%d"),
        **arbitrage
    }


@router.get("/recommendation/{building_id}", response_model=Dict)
async def get_realtime_recommendation(
    building_id: str,
    db: AsyncSession = Depends(get_db)
):
    """지금 당장 권고 행동"""
    device_repo = DeviceRepository(db)
    sensor_repo = SensorRepository(db)
    
    # 디바이스 조회
    devices = await device_repo.list_by_building(building_id)
    grid_device = next((d for d in devices if d.device_type == "grid"), None)
    ess_device = next((d for d in devices if d.device_type == "ess"), None)

    # 현재 상태 조회
    grid_current = 0.0
    ess_soc = 50.0
    threshold = 10.0

    if grid_device:
        grid_reading = await sensor_repo.get_latest(grid_device.device_id, "grid_current")
        if grid_reading:
            grid_current = grid_reading.value

    if ess_device:
        soc_reading = await sensor_repo.get_latest(ess_device.device_id, "ess_soc")
        if soc_reading:
            ess_soc = soc_reading.value

    recommendation = optimizer.get_realtime_recommendation(ess_soc, grid_current, threshold)

    return {
        "building_id": building_id,
        "timestamp": datetime.now().isoformat(),
        **recommendation
    }

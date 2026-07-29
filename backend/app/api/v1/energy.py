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


def _now_kst():
    """KST 벽시계 (서버가 UTC여도 한국 시간 기준으로 판정)."""
    from datetime import datetime as _dt, timedelta as _td
    return _dt.utcnow() + _td(hours=9)


try:
    from app.ml.xgboost_forecaster import XGBoostForecaster
except ImportError:
    XGBoostForecaster = None

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
    """오늘 차익 — 요금표 기반 예시 시나리오 계산.

    충방전량(5.0/4.5 kWh)은 고정 시나리오다. 실측 연동은 하드웨어 텔레메트리의
    INA 전류·전압(방전 전력)을 적산해야 하는데, 백엔드 sensor_type이
    grid_current/ess_soc/charger_current 3종뿐이라 스키마 확장이 선행돼야 한다.
    그 전까지 응답에 is_example을 명시해 화면이 '실시간 계산'으로 과장하지 않게 한다.
    """
    season = optimizer._get_season(_now_kst())
    arbitrage = optimizer.calculate_arbitrage(
        charged_kwh=5.0,
        discharged_kwh=4.5,
        charge_period="경부하",
        discharge_period="최대부하",
        season=season
    )

    return {
        "building_id": building_id,
        "date": _now_kst().strftime("%Y-%m-%d"),
        "is_example": True,
        "charged_kwh": 5.0,
        "discharged_kwh": 4.5,
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
    from app.services.scenario_service import get_threshold

    grid_current = 0.0
    ess_soc = 50.0
    # 컨트롤 탭 슬라이더가 설정한 건물별 임계치 (실측 스케일 0.0x A).
    # 고정값을 쓰면 방전 권고·urgency 판정이 실측 전류에서 영구히 죽는다.
    threshold = get_threshold(building_id)

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
        "timestamp": _now_kst().isoformat(),
        **recommendation
    }


@router.get("/model-info", response_model=Dict)
async def get_model_info():
    """현재 사용 중인 모델 정보 반환"""
    # XGBoost 모델 먼저 시도
    if XGBoostForecaster is not None:
        try:
            forecaster = XGBoostForecaster("building-A")
            if forecaster.load():
                return forecaster.get_model_info()
        except Exception:
            pass

    # 기본 모델 정보 반환
    return {
        "model_type": "Prophet/LinearRegression",
        "training_data": "자체 수집 데이터",
        "features": ["hour", "weekday", "is_weekend"],
        "mae": None,
        "trained_at": None
    }

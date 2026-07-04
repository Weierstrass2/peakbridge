"""AI 기반 추천 및 시나리오 API."""

from fastapi import APIRouter, Query

from app.core.deps import DbSession, get_mqtt_publisher
from app.repositories.sensor_repository import SensorRepository
from app.schemas.response import success_response
from app.services.kepco_service import KepcoService
from app.services.ppo_service import PPOService
from app.services.scenario_service import ScenarioService
from app.services.weather_service import WeatherService

router = APIRouter(prefix="/ai", tags=["ai"])

_ppo_service = PPOService()


@router.get("/recommend/{building_id}")
async def get_recommendation(
    session: DbSession,
    building_id: str,
) -> dict:
    """PPO 모델 기반 ESS 제어 추천."""
    sensor_repo = SensorRepository(session)
    weather_service = WeatherService()
    kepco_service = KepcoService()

    # 센서 데이터 조회
    grid_reading = await sensor_repo.get_latest_by_building(
        building_id, "grid_current", "grid"
    )
    ess_reading = await sensor_repo.get_latest_by_building(
        building_id, "ess_soc", "ess"
    )

    grid_current = grid_reading.value if grid_reading else 0.0
    ess_soc = ess_reading.value if ess_reading else 50.0

    # 외부 데이터 조회
    current_temp = await weather_service.get_current_temperature()
    tariff_info = kepco_service.get_current_tariff_info()
    tariff_rate = tariff_info[1]

    # 추천 받기
    recommendation = await _ppo_service.get_recommendation(
        building_id=building_id,
        grid_current=grid_current,
        ess_soc=ess_soc,
        current_temp=current_temp,
        tariff_rate=tariff_rate,
    )

    return success_response(recommendation)


@router.get("/scenarios/{building_id}")
async def get_scenarios(
    session: DbSession,
    building_id: str,
) -> dict:
    """5가지 시나리오 상태 조회."""
    mqtt = get_mqtt_publisher()
    scenario_service = ScenarioService(session, mqtt)
    scenarios = await scenario_service.evaluate_scenarios(building_id)
    return success_response(scenarios)

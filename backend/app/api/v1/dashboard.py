"""대시보드 API — 건물별 실시간 상태."""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.constants import DeviceType, SensorType
from app.core.deps import DbSession
from app.repositories.alert_repository import AlertRepository
from app.repositories.device_repository import DeviceRepository
from app.repositories.energy_repository import EnergyRepository
from app.repositories.sensor_repository import SensorRepository
from app.schemas.response import success_response
from app.services.forecast_service import ForecastService
from app.services.scenario_service import (
    get_threshold,
    effective_now_utc,
    get_demo_time,
    get_ess_runtime,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/{building_id}")
async def get_dashboard(session: DbSession, building_id: str) -> dict:
    """
    GET /api/v1/dashboard/{building_id}

    건물별 실시간 피크쉐이빙 대시보드 데이터.
    """
    sensor_repo = SensorRepository(session)
    device_repo = DeviceRepository(session)
    alert_repo = AlertRepository(session)
    energy_repo = EnergyRepository(session)
    forecast_svc = ForecastService(session)

    grid = await sensor_repo.get_latest_by_building(
        building_id, SensorType.GRID_CURRENT.value, DeviceType.GRID_METER.value
    )
    ess = await sensor_repo.get_latest_by_building(
        building_id, SensorType.ESS_SOC.value, DeviceType.ESS.value
    )

    chargers = await device_repo.list_by_building(
        building_id, DeviceType.CHARGER.value
    )
    charger_data = []
    for charger in chargers:
        latest = await sensor_repo.get_latest(
            charger.device_id, SensorType.CHARGER_CURRENT.value
        )
        charger_data.append(
            {
                "device_id": charger.device_id,
                "current": latest.value if latest else 0.0,
                "status": charger.status,
            }
        )

    today = await energy_repo.get_by_date(building_id, datetime.now(timezone.utc).date())
    month_saved = await energy_repo.get_month_total(building_id)

    real_now = datetime.now(timezone.utc)
    demo_dt = get_demo_time()
    try:
        # 예측 시각열(time)만 사용 — 데모 시각(있으면) 기준으로 향후 60분
        forecast = await forecast_svc.predict(building_id)
    except Exception:
        forecast = []
    peak_active = await alert_repo.has_active_peak(building_id)

    threshold = get_threshold(building_id)
    actual_current = grid.value if grid else 0.0

    # 시간대 프로파일 배율로 예측을 구성한다.
    # XGBoost는 실측 lag 없이 합성 학습돼(더미 lag 고정) 시간대 반응이 약하므로,
    # 실측 데이터로 재학습하기 전까지는 명시적 시간대 배율을 쓴다.
    #   기저부하 = 현재 실측 전류 / (현재 시각 배율)   ← 실측 반응(부하 올리면 상승)
    #   예측값   = 기저부하 × (예측 시각 배율)          ← 시간대 반응(피크대로 옮기면 상승)
    def _hour_factor(kst_hour: int) -> float:
        if 18 <= kst_hour <= 21:
            return 1.6           # 저녁 피크
        if kst_hour in (11, 12, 13, 17):
            return 1.3           # 낮 준피크
        if kst_hour >= 23 or kst_hour < 7:
            return 0.6           # 심야 경부하
        return 1.0

    if forecast and actual_current > 0:
        real_kst = (real_now.hour + 9) % 24
        base_load = actual_current / _hour_factor(real_kst)
        for p in forecast:
            t = p["time"]
            t_dt = datetime.fromisoformat(t) if isinstance(t, str) else t
            kst_h = (t_dt.hour + 9) % 24
            val = base_load * _hour_factor(kst_h)
            p["predicted_current"] = round(val, 4)
            p["lower"] = round(val * 0.9, 4)
            p["upper"] = round(val * 1.1, 4)
            p["will_exceed"] = val > threshold

    # 다음 피크 예상: will_exceed=True인 첫 예측점 (없으면 None)
    now_eff = effective_now_utc()
    next_peak = None
    for p in forecast:
        if p.get("will_exceed"):
            t = p["time"]
            t_dt = datetime.fromisoformat(t) if isinstance(t, str) else t
            if t_dt.tzinfo is None:
                t_dt = t_dt.replace(tzinfo=timezone.utc)
            minutes_ahead = max(0, round((t_dt - now_eff).total_seconds() / 60))
            next_peak = {
                "time": t_dt.isoformat(),
                "predicted_current": p["predicted_current"],
                "minutes_ahead": minutes_ahead,
            }
            break

    demo_dt = get_demo_time()
    ess_rt = get_ess_runtime(building_id)
    data = {
        "grid_current": actual_current,
        "ess_soc": ess.value if ess else 0.0,
        "ess_remain_hours": ess_rt["remain_hours"] if ess_rt else None,
        "peak_active": peak_active,
        "peak_threshold": threshold,
        "next_peak": next_peak,
        "demo_time": demo_dt.isoformat() if demo_dt else None,
        "chargers": charger_data,
        "forecast": forecast,
        "today_saved_won": today.saved_won if today else 0.0,
        "month_saved_won": month_saved,
        "co2_reduced_kg": today.co2_reduced_kg if today else 0.0,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    return success_response(data)

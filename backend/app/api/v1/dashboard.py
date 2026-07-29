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
from app.services.scenario_service import get_threshold, effective_now_utc, get_demo_time

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
        # 표시용 예측: 데모 시각(있으면) 기준
        forecast = await forecast_svc.predict(building_id)
        # 앵커 기준값: 항상 '실제 현재 시각'의 모델 예측 첫 점.
        # 이래야 데모 시각을 피크시간대로 옮겼을 때의 절대 상승이 살아난다.
        if demo_dt is not None:
            real_fc = await forecast_svc.predict(building_id, now_override=real_now)
            base_ref = real_fc[0]["predicted_current"] if real_fc else None
        else:
            base_ref = forecast[0]["predicted_current"] if forecast else None
    except Exception:
        forecast = []
        base_ref = None
    peak_active = await alert_repo.has_active_peak(building_id)

    threshold = get_threshold(building_id)
    actual_current = grid.value if grid else 0.0

    # 실측 스케일 앵커링: XGBoost 모델은 합성 데이터(수~십 A) 스케일로 학습돼 있어,
    # 예측선의 '시간대 모양'은 살리되 스케일은 현재 실측 전류에 맞춘다.
    # ratio = 실측 현재값 / (실제 현재 시각의 모델 예측값).
    #   · 부하를 올리면 actual_current↑ → 예측선 전체 상승 (실측 반응)
    #   · 데모 시각을 피크시간대로 옮기면 모델 패턴이 상대적으로 높아 → will_exceed (예측 반응)
    if forecast and actual_current > 0 and base_ref and base_ref > 0:
        ratio = actual_current / base_ref
        for p in forecast:
            p["predicted_current"] = round(p["predicted_current"] * ratio, 4)
            p["lower"] = round(p["lower"] * ratio, 4)
            p["upper"] = round(p["upper"] * ratio, 4)
            p["will_exceed"] = p["predicted_current"] > threshold

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
    data = {
        "grid_current": actual_current,
        "ess_soc": ess.value if ess else 0.0,
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

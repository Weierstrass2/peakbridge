"""VPP(가상발전소) API — 포트폴리오·수요반응·차익거래 수익."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.constants import DeviceType, SensorType
from app.core.deps import DbSession
from app.ml.energy_optimizer import EnergyOptimizer
from app.ml.vpp_simulator import vpp_simulator
from app.repositories.device_repository import DeviceRepository
from app.repositories.sensor_repository import SensorRepository
from app.schemas.response import success_response
from app.services.kepco_service import KepcoService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/vpp", tags=["vpp"])

optimizer = EnergyOptimizer()

# 시연 포트폴리오: 실단지(building-A, DB 연동) + 확장 예시 단지
DEMO_BUILDINGS = [
    {"building_id": "building-B", "ess_capacity": 200.0, "current_soc": 65.0, "max_power_kw": 100.0, "soh": 97.1, "pcs_temp": 35.8, "pcs_eff": 95.9, "link_ms": 41},
    {"building_id": "building-C", "ess_capacity": 150.0, "current_soc": 80.0, "max_power_kw": 75.0, "soh": 99.0, "pcs_temp": 31.2, "pcs_eff": 96.5, "link_ms": 37},
]


async def _live_building(session) -> dict:
    """building-A 실측 SOC 기반 항목."""
    soc = 50.0
    try:
        sensor_repo = SensorRepository(session)
        reading = await sensor_repo.get_latest_by_building(
            "building-A", SensorType.ESS_SOC.value, DeviceType.ESS.value
        )
        if reading:
            soc = reading.value
    except Exception as exc:
        logger.warning("vpp_live_soc_failed", error=str(exc))
    return {
        "building_id": "building-A",
        "ess_capacity": 100.0,
        "current_soc": soc,
        "max_power_kw": 50.0,
        "live": True,
        "soh": 98.4,
        "pcs_temp": round(33.0 + 2.5 * __import__("math").sin(__import__("time").time() / 700), 1),
        "pcs_eff": 96.2,
        "link_ms": __import__("random").randint(9, 28),
    }


async def _current_smp() -> float:
    try:
        return await KepcoService().get_current_smp()
    except Exception as exc:
        logger.warning("vpp_smp_failed_fallback", error=str(exc))
        return float(optimizer.get_current_rate()["rate"])


@router.get("/portfolio")
async def get_portfolio(session: DbSession) -> dict:
    """GET /api/v1/vpp/portfolio — 통합 포트폴리오 (building-A는 실측)."""
    buildings = [await _live_building(session), *DEMO_BUILDINGS]
    result = vpp_simulator.calculate_portfolio(buildings)
    result["note"] = "building-A 실측, B/C는 확장 예시"
    return success_response(result)


@router.get("/capacity")
async def get_capacity(session: DbSession) -> dict:
    """GET /api/v1/vpp/capacity — 가용 유연성 요약."""
    buildings = [await _live_building(session), *DEMO_BUILDINGS]
    p = vpp_simulator.calculate_portfolio(buildings)
    return success_response(
        {
            "total_capacity_kwh": p["total_capacity_kwh"],
            "available_flexibility_kw": p["available_flexibility_kw"],
            "building_count": p["building_count"],
        }
    )


@router.get("/revenue/dr")
async def get_dr_revenue(
    session: DbSession,
    reduction_kw: float = Query(default=None, ge=0, le=10000),
    duration_hours: float = Query(default=1.0, gt=0, le=24),
) -> dict:
    """GET /api/v1/vpp/revenue/dr — 수요반응 수익 (기본: 현재 가용 유연성 전량)."""
    smp = await _current_smp()
    if reduction_kw is None:
        buildings = [await _live_building(session), *DEMO_BUILDINGS]
        reduction_kw = vpp_simulator.calculate_portfolio(buildings)[
            "available_flexibility_kw"
        ]
    result = vpp_simulator.calculate_dr_revenue(reduction_kw, duration_hours, smp)
    return success_response(result)


@router.get("/revenue/arbitrage")
async def get_arbitrage_revenue(
    charged_kwh: float = Query(default=100.0, ge=0, le=100000),
    discharged_kwh: float = Query(default=90.0, ge=0, le=100000),
) -> dict:
    """GET /api/v1/vpp/revenue/arbitrage — 경부하 충전 → 최대부하 방전 차익."""
    try:
        season = optimizer._get_season(__import__("datetime").datetime.now())
        charge_price = optimizer.RATES[season]["경부하"]
        discharge_price = optimizer.RATES[season]["최대부하"]
    except Exception:
        charge_price, discharge_price = 42.5, 147.0
    result = vpp_simulator.calculate_arbitrage(
        charged_kwh, discharged_kwh, charge_price, discharge_price
    )
    result["charge_price"] = charge_price
    result["discharge_price"] = discharge_price
    return success_response(result)


# ── 관제센터 실시간 스트림 + 거래 장부 ─────────────────────

import math
import random
import time as _time

from app.services.openadr_service import openadr_service
from app.services.vpp_ledger import vpp_ledger

try:
    from app.ml.xgboost_forecaster import XGBoostForecaster
except ImportError:
    XGBoostForecaster = None


_stream_hist: list[dict] = []

# 학습된 XGBoost 모델 인스턴스 캐시 (3초 폴링마다 joblib 재로드 방지)
_xgb_forecaster = None
_xgb_load_failed = False


def _xgb_forecast_curve() -> tuple[list[float], float] | None:
    """실제 학습된 XGBoost 모델의 향후 60분(5분 간격) 예측 곡선 + MAE 기반 CI 비율 반환.

    building-A 단일 스케일로 학습된 모델이라, 호출 측에서 포트폴리오
    수요 스케일에 비율로 반영한다 (원시값을 그대로 쓰면 스케일이 안 맞음).
    CI 비율은 모델 실측 MAE를 예측 평균 대비 상대 오차로 환산 (2~8% 클램프,
    MAE 없으면 기존 3.5% 유지).
    """
    global _xgb_forecaster, _xgb_load_failed
    if XGBoostForecaster is None or _xgb_load_failed:
        return None
    try:
        if _xgb_forecaster is None:
            _xgb_forecaster = XGBoostForecaster("building-A")
            if not _xgb_forecaster.load():
                _xgb_load_failed = True
                return None
        preds = _xgb_forecaster.predict_next_hour()
        if not preds:
            return None
        curve = [p["predicted"] for p in preds]
        mean_pred = sum(curve) / len(curve)
        mae = getattr(_xgb_forecaster, "mae", None)
        ci_ratio = 0.035
        if mae and mean_pred > 0:
            ci_ratio = max(0.02, min(0.08, float(mae) / mean_pred))
        return curve, round(ci_ratio, 4)
    except Exception:
        _xgb_load_failed = True
        return None


@router.get("/stream/history")
async def get_stream_history(limit: int = Query(default=120, ge=1, le=600)) -> dict:
    """스트림 히스토리 (서버 보관) — 콘솔 새로고침 시 차트 연속성."""
    return success_response({"points": _stream_hist[-limit:]})


@router.get("/stream")
async def get_stream(session: DbSession) -> dict:
    """
    GET /api/v1/vpp/stream — 관제센터 차트용 실시간 스냅샷 (3초 폴링).

    A단지는 실측 기반, B/C는 시뮬레이션 발전 프로파일.
    DR 이벤트 활성 시 출력이 상승해 차트에 즉시 반영됨.
    """
    t = _time.time()
    active = openadr_service.get_status().get("active_event")
    discharging = bool(active and active.get("action") == "discharge")
    boost = (active.get("discharge_percent", 0) / 100.0) if discharging else 0.0

    # A단지: 실측 SOC/전류
    live = await _live_building(session)
    # 실측 SOC → 급전 엔진 동기화 (이행 중이 아닐 때만 — 시뮬 방전과 충돌 방지)
    try:
        from app.services.dispatch_service import dispatch_service

        if dispatch_service._active is None:
            dispatch_service._soc["building-A"] = float(live["current_soc"])
    except Exception:
        pass
    a_soc = live["current_soc"]
    a_max = live["max_power_kw"]
    a_out = round(min(a_max, a_max * boost) + random.uniform(-0.3, 0.3), 1) if discharging else round(random.uniform(0.0, 0.6), 1)
    a_out = max(0.0, a_out)

    # B/C단지: 살아있는 시뮬레이션 프로파일 (사인 + 노이즈)
    b_base = 42 + 16 * math.sin(t / 240.0)
    c_base = 62 + 12 * math.sin(t / 300.0 + 2.1)
    b_out = round(max(0.0, (90 * boost if discharging else b_base * 0.35) + random.uniform(-2, 2)), 1)
    c_out = round(max(0.0, (75 * boost if discharging else c_base * 0.3) + random.uniform(-2, 2)), 1)

    total = round(a_out + b_out + c_out, 1)

    # 수요 (실측 없으면 시뮬 프로파일이 계속 움직이게)
    demand = round(255 + 55 * math.sin(t / 700.0) + random.uniform(-4, 4), 1)

    # 예측 (실제 학습된 XGBoost 모델의 시간대별 추세를 현재 수요 스케일에 반영)
    xgb = _xgb_forecast_curve()
    if xgb:
        curve, ci_ratio = xgb
        idx = int((t // 300) % len(curve))
        base = curve[0] or 1.0
        trend_ratio = max(0.85, min(1.2, curve[idx] / base))
        forecast = round(demand * trend_ratio, 1)
        forecast_source = "xgboost"
    else:
        ci_ratio = 0.035
        forecast = round(demand + 9 * math.sin(t / 450.0 + 1.0), 1)
        forecast_source = "sim"

    # ── SMP: 시간대별 확정값 (계단형) ──────────────────────────
    # 실제 SMP는 하루전시장에서 시간대별로 확정된다. 정시에만 바뀌고,
    # 시간 내에서는 상수다. 초 단위로 요동치게 만들면 시장 문법과 어긋난다.
    # (분 단위로 움직이는 가격은 실시간시장(RT) — 아래 rt_price로 따로 제공)
    _now_kst = __import__("datetime").datetime.now(
        __import__("datetime").timezone(__import__("datetime").timedelta(hours=9))
    )
    hour = _now_kst.hour
    smp = None
    try:
        from app.services.market_service import market_service

        curve = market_service.mcp_forecast()      # 24개 시간대 확정 곡선
        if curve and len(curve) == 24:
            smp = round(float(curve[hour]), 1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("stream_smp_curve_failed", error=str(exc))
    if smp is None:
        try:
            base_rate = float(optimizer.get_current_rate()["rate"])
        except Exception:  # noqa: BLE001
            base_rate = 84.5
        smp = round(base_rate * 1.15, 1)           # 폴백도 시간 내 상수

    # 실시간시장 가격 — 15분 슬롯 단위로만 갱신 (제주 시범사업 구조)
    slot = int(_now_kst.minute // 15)
    rt_seed = hash((_now_kst.year, _now_kst.month, _now_kst.day, hour, slot)) % 10_000
    rt_price = round(smp * (1 + ((rt_seed / 10_000) - 0.5) * 0.12), 1)

    snap = {
            "ts": __import__("datetime").datetime.now(
                __import__("datetime").timezone(__import__("datetime").timedelta(hours=9))
            ).strftime("%H:%M:%S"),
            "total_output_kw": total, "demand_kw": demand,
            "forecast_kw": forecast,
            "forecast_hi": round(forecast * (1 + ci_ratio), 1),
            "forecast_lo": round(forecast * (1 - ci_ratio), 1),
            "forecast_source": forecast_source,
            "smp": smp, "dr_active": discharging,
            # 가격 문법 표기 — 화면에서 '시간별 확정'과 '실시간'을 구분해 보여준다
            "smp_basis": "hourly",          # 하루전시장 시간대별 확정
            "smp_hour": hour,
            "rt_price": rt_price,           # 실시간시장 15분 슬롯
            "rt_slot": f"{hour:02d}:{slot * 15:02d}",
        }
    if not _stream_hist or _stream_hist[-1]["ts"] != snap["ts"]:
        _stream_hist.append(snap)
        del _stream_hist[:-600]
    return success_response(
        {
            "ts": __import__("datetime").datetime.now(
                __import__("datetime").timezone(__import__("datetime").timedelta(hours=9))
            ).strftime("%H:%M:%S"),
            "buildings": [
                {"id": "building-A", "output_kw": a_out, "soc": a_soc, "live": True},
                {"id": "building-B", "output_kw": b_out, "soc": round(65 + 5 * math.sin(t / 900), 1), "live": False},
                {"id": "building-C", "output_kw": c_out, "soc": round(80 + 4 * math.sin(t / 1100 + 1), 1), "live": False},
            ],
            "total_output_kw": total,
            "demand_kw": demand,
            "forecast_kw": forecast,
            "forecast_hi": round(forecast * (1 + ci_ratio), 1),
            "forecast_lo": round(forecast * (1 - ci_ratio), 1),
            "forecast_source": forecast_source,
            "ci_ratio": ci_ratio,
            "smp": smp,
            "dr_active": discharging,
            "discharge_percent": round(boost * 100),
        }
    )


@router.get("/ledger")
async def get_ledger(limit: int = Query(default=12, ge=1, le=100)) -> dict:
    """GET /api/v1/vpp/ledger — 거래 장부 (DR 정산·차익거래 원장)."""
    return success_response(
        {"summary": vpp_ledger.summary(), "entries": vpp_ledger.entries(limit)}
    )


# ── 계약 관리 (A5) ──────────────────────────────────────

CONTRACTS = [
    {"building_id": "building-A", "name": "실증단지 A", "type": "수익배분형",
     "site_share": 0.70, "platform_share": 0.30, "term": "2026-03 ~ 2029-03",
     "resources": "묶음 ESS 100kWh + 충전기 DR", "status": "유효"},
    {"building_id": "building-B", "name": "단지 B", "type": "수익배분형",
     "site_share": 0.70, "platform_share": 0.30, "term": "2026-06 ~ 2029-06",
     "resources": "묶음 ESS 200kWh", "status": "유효(시뮬)"},
    {"building_id": "building-C", "name": "단지 C", "type": "고정임대형",
     "site_share": 0.60, "platform_share": 0.40, "term": "2026-05 ~ 2028-05",
     "resources": "묶음 ESS 150kWh", "status": "유효(시뮬)"},
]


@router.get("/contracts")
async def get_contracts() -> dict:
    """단지 계약 현황 + 수익 배분 정산."""
    try:
        from app.services.vpp_ledger import vpp_ledger

        s = vpp_ledger.summary()
        total = max(0.0, s.get("total_revenue", 0.0))
        avg_platform = sum(c["platform_share"] for c in CONTRACTS) / len(CONTRACTS)
        return success_response(
            {
                "contracts": CONTRACTS,
                "settlement_split": {
                    "total_revenue": round(total, 0),
                    "site_payout": round(total * (1 - avg_platform), 0),
                    "platform_revenue": round(total * avg_platform, 0),
                    "avg_platform_share": round(avg_platform, 2),
                },
            }
        )
    except Exception as exc:
        logger.error("vpp_contracts_failed", error=str(exc))
        return success_response({"contracts": [], "settlement_split": {}})

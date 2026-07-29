"""전력시장(DAM) 입찰 API — 입찰서 작성·제출·개찰."""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.schemas.response import success_response
from app.services.market_service import market_service
from app.services.ops_service import ops_service
from app.services.bid_ai import ai_bids
from app.services.strategy_service import strategy_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/market", tags=["market"])


class BidItem(BaseModel):
    hour: int = Field(ge=0, le=23)
    qty_kw: float = Field(ge=0, le=500)
    price: float = Field(ge=0, le=500)


class BidSheet(BaseModel):
    bids: list[BidItem] = Field(max_length=24)


@router.get("/session")
async def get_session() -> dict:
    """현재 입찰 세션 (입찰서·상태·마감 카운트다운)."""
    try:
        return success_response(market_service.get_session())
    except Exception as exc:
        logger.error("market_session_failed", error=str(exc))
        return success_response({"status": "error"})


@router.post("/bids")
async def save_bids(body: BidSheet) -> dict:
    """입찰서 저장 (draft)."""
    try:
        return success_response(
            market_service.save_bids([b.model_dump() for b in body.bids])
        )
    except Exception as exc:
        logger.error("market_save_failed", error=str(exc))
        return success_response({"status": "error"})


@router.post("/submit")
async def submit_bids() -> dict:
    """입찰서 제출."""
    try:
        r = market_service.submit()
        ops_service.audit('operator', 'BID_SUBMIT', f"세션 {r.get('session_id')} 입찰 제출")
        return success_response(r)
    except Exception as exc:
        logger.error("market_submit_failed", error=str(exc))
        return success_response({"status": "error"})


@router.post("/clear")
async def clear_market() -> dict:
    """개찰 (시연용 수동 트리거) — 낙찰 판정 + 예상 정산."""
    try:
        r = market_service.clear()
        res = r.get('results') or {}
        ops_service.audit('operator', 'MARKET_CLEAR', f"세션 {r.get('session_id')} 개찰 — {res.get('awarded_hours')}구간 낙찰")
        ops_service.alarm('INFO', 'market', f"개찰 완료 — 낙찰 {res.get('awarded_hours')}구간, 예상 ₩{int(res.get('total_expected_revenue', 0)):,}")
        return success_response(r)
    except Exception as exc:
        logger.error("market_clear_failed", error=str(exc))
        return success_response({"status": "error"})


@router.get("/mcp-forecast")
async def get_mcp_forecast() -> dict:
    """내일 시장청산가격 예상 곡선 (입찰 참고)."""
    try:
        return success_response({"curve": market_service.mcp_forecast()})
    except Exception as exc:
        logger.error("market_mcp_failed", error=str(exc))
        return success_response({"curve": []})


@router.get("/ai-bids")
async def get_ai_bids() -> dict:
    """학습된 정책 신경망의 추천 입찰 곡선."""
    try:
        forecast = market_service.mcp_forecast()
        return success_response(ai_bids(forecast))
    except Exception as exc:
        logger.error("market_ai_bids_failed", error=str(exc))
        return success_response({"bids": []})


# ── 전략 라이브러리 · 백테스트 리더보드 ─────────────────────

@router.get("/strategies")
async def list_strategies() -> dict:
    """자동매매 전략 목록 + 백테스트 성과 (활성 전략 표시)."""
    try:
        return success_response({
            "active": strategy_service.active,
            "strategies": strategy_service.catalog(),
        })
    except Exception as exc:
        logger.error("strategy_list_failed", error=str(exc))
        return success_response({"active": None, "strategies": []})


@router.get("/strategies/leaderboard")
async def strategy_leaderboard() -> dict:
    """백테스트 리더보드 원본 (scripts/benchmark_strategies.py 산출물)."""
    try:
        return success_response(strategy_service.leaderboard())
    except Exception as exc:
        logger.error("strategy_leaderboard_failed", error=str(exc))
        return success_response({"leaderboard": []})


class StrategySelect(BaseModel):
    name: str = Field(description="활성화할 전략 이름")


@router.post("/strategies/activate")
async def activate_strategy(body: StrategySelect) -> dict:
    """운영 입찰에 사용할 전략 교체 (in-memory — 재시작 시 기본값 복귀)."""
    try:
        return success_response(strategy_service.set_active(body.name))
    except ValueError as exc:
        return success_response({"error": str(exc)})


@router.get("/strategy-bids")
async def get_strategy_bids(
    strategy: str | None = None,
    contract_kw: float = 200.0,
    month_peak_kw: float = 0.0,
    lookback_months: int = 1,
    reserve: bool = True,
) -> dict:
    """활성(또는 지정) 전략의 추천 입찰 곡선.

    reserve=True 이면 **피크 예약이 먼저 적용된다.**
    아파트 수요예측으로 그날 피크 위험 구간을 잡아 배터리를 잠그고,
    남은 에너지만 시장 입찰에 넘긴다. 기본요금 방어가 시장 판매보다 우선이다.
    """
    try:
        forecast = market_service.mcp_forecast()
        demand = _demand_curve() if reserve else None
        return success_response(strategy_service.build_bids(
            forecast, strategy=strategy, demand_kw=demand,
            contract_kw=contract_kw if reserve else 0.0,
            month_peak_kw=month_peak_kw, lookback_months=lookback_months,
        ))
    except Exception as exc:
        logger.error("strategy_bids_failed", error=str(exc))
        return success_response({"bids": []})


def _demand_curve() -> list[float]:
    """오늘의 시간대별 예상 부하 (kW).

    실측 수요 이력이 있으면 그 형상을 쓰고, 없으면 아파트 전형 곡선으로 폴백한다.
    (저녁 피크가 뚜렷한 주거 부하 패턴)
    """
    try:
        from app.services import market_data

        market_data._load_once()
        from datetime import datetime

        now = datetime.now(_KST)
        vals = [market_data._dpct.get((now.year, now.month, now.day, h)) for h in range(24)]
        if all(v is not None for v in vals):
            # 수요 백분위(0~1) → kW 스케일 (계약전력 200kW 단지 기준 형상)
            return [round(60.0 + 170.0 * float(v), 1) for v in vals]  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        pass
    return [95, 90, 88, 86, 85, 88, 100, 120, 140, 155, 170, 185,
            195, 205, 215, 225, 220, 210, 195, 180, 165, 140, 120, 105]


@router.get("/peak-reservation")
async def peak_reservation(
    contract_kw: float = 200.0,
    month_peak_kw: float = 0.0,
    lookback_months: int = 1,
) -> dict:
    """피크 예약 상세 — 오늘 배터리를 얼마나 잠글 것인가.

    이 사업의 우선순위를 숫자로 드러낸다:
    **관리비 방어가 먼저이고, 시장 판매는 남는 것으로 한다.**
    """
    try:
        from app.core.resources import ess_resources
        from app.services.strategies.reservation import compare_uses, plan_reservation

        res = ess_resources()
        power = sum(r["max_discharge_kw"] for r in res.values())
        energy = sum(
            max(0.0, 60.0 - r["soc_min"]) / 100 * r["capacity_kwh"] for r in res.values()
        )
        demand = _demand_curve()
        forecast = market_service.mcp_forecast()
        plan = plan_reservation(
            demand_kw=demand, contract_kw=contract_kw, power_kw=power,
            energy_kwh=energy, month_peak_kw=month_peak_kw,
            lookback_months=lookback_months,
        )
        out = plan.to_dict()
        out["comparison"] = compare_uses(plan, forecast)
        out["demand_kw"] = demand
        out["forecast"] = forecast
        out["usable_kwh"] = round(energy, 1)
        out["sellable_kwh"] = round(max(0.0, energy - plan.reserved_kwh), 1)
        out["contract_kw"] = contract_kw
        return success_response(out)
    except Exception as exc:  # noqa: BLE001
        logger.error("peak_reservation_failed", error=str(exc))
        return success_response({})


@router.get("/profiles")
async def market_profiles() -> dict:
    """시장 프로파일 — 육지(현행 CBP) vs 제주(시범사업) 참여 문법 비교.

    같은 자원·같은 엔진이지만 시장 문법이 다르다는 것을 명시적으로 드러낸다.
    """
    try:
        from app.core.market_profiles import compare

        return success_response(compare())
    except Exception as exc:  # noqa: BLE001
        logger.error("market_profiles_failed", error=str(exc))
        return success_response({"profiles": []})


@router.get("/profile")
async def market_profile(key: str | None = None) -> dict:
    """현재(또는 지정) 시장 프로파일 상세."""
    try:
        import os

        from app.core.market_profiles import DEFAULT_PROFILE, get_profile

        # KPX_REGION 설정을 존중한다 (jeju면 제주 프로파일)
        auto = "jeju_pilot" if os.environ.get("KPX_REGION", "").lower() == "jeju" else DEFAULT_PROFILE
        return success_response(get_profile(key or auto).to_dict())
    except Exception as exc:  # noqa: BLE001
        logger.error("market_profile_failed", error=str(exc))
        return success_response({})


@router.get("/jeju/plusdr")
async def jeju_plusdr(incentive: float = 120.0, sites: int = 100) -> dict:
    """제주 플러스 DR 참여 분석 — 실측 기반.

    이 화면이 말하는 것:
      1. 출력제어 시각에도 SMP는 173원이다 (공짜 전기는 없다)
      2. 그래서 정부가 별도 인센티브로 수요를 끌어올린다 = 플러스 DR
      3. 낙찰률 100% — 경쟁이 없다
      4. 이행률 41.7% — 낙찰자도 못 지킨다. **이행하면 손해기 때문이다**
      5. 이벤트가 최대부하 시간대라 충전이 기본요금을 밀어 올린다
      6. 피크 예약 엔진이 있으면 이행하면서 기본요금도 안 올린다 ← 우리 자리
    """
    try:
        from app.services.strategies.plusdr import Fleet, compare

        return success_response(compare(Fleet(sites=sites), incentive))
    except Exception as exc:  # noqa: BLE001
        logger.error("jeju_plusdr_failed", error=str(exc))
        return success_response({"leaderboard": []})


@router.get("/jeju/facts")
async def jeju_facts() -> dict:
    """제주 실측 통계 원본 — 출력제어·플러스DR·예측정확도·수급."""
    try:
        import json
        from pathlib import Path

        p = Path(__file__).resolve().parents[3] / "data" / "jeju_facts.json"
        if not p.exists():
            return success_response({"loaded": False,
                                     "hint": "python scripts/ingest_jeju_real.py 실행 필요"})
        d = json.loads(p.read_text(encoding="utf-8"))
        d["loaded"] = True
        return success_response(d)
    except Exception as exc:  # noqa: BLE001
        logger.error("jeju_facts_failed", error=str(exc))
        return success_response({"loaded": False})


@router.get("/jeju/leaderboard")
async def jeju_leaderboard(days: int = 180, spread_scale: float = 0.41,
                           behind_meter: bool = False) -> dict:
    """제주 실시간시장 전략 리더보드.

    spread_scale  — 일중 변동폭 가정 배율. 0.41이면 육지 실측과 같은 수준의
                    스프레드를 가정한 보수적 시나리오다.
    behind_meter  — 자산이 계량기 어느 쪽에 있는가.
                    True(아파트)면 시장가가 아니라 계시별 요금으로 거래하므로
                    출력제어의 공짜 전력에 접근할 수 없다.
    """
    try:
        from app.services.strategies.jeju import Asset, JejuMarketModel, leaderboard as jlb

        return success_response(jlb(
            days=days,
            model=JejuMarketModel(spread_scale=spread_scale),
            asset=Asset(behind_meter=behind_meter),
        ))
    except Exception as exc:  # noqa: BLE001
        logger.error("jeju_leaderboard_failed", error=str(exc))
        return success_response({"leaderboard": []})


@router.get("/jeju/site-compare")
async def jeju_site_compare(days: int = 120) -> dict:
    """자산 위치 비교 — 같은 전략, 계량기 안 vs 밖.

    이 사업에서 가장 자주 오해되는 지점을 숫자로 못박는다:
    **아파트 배터리로는 제주 출력제어를 흡수할 수 없다.**
    계량기 안쪽 자산은 도매 시장가가 0원이 되어도 소매 요금을 내기 때문이다.
    """
    try:
        from app.services.strategies.jeju import (
            Asset, CurtailAbsorb, DayAheadOnly, JejuMarketModel, RollingRT, backtest,
        )

        model = JejuMarketModel(spread_scale=0.41)
        out = []
        for site, bm in [("발전연계 (계량기 밖)", False), ("아파트 (계량기 안)", True)]:
            asset = Asset(behind_meter=bm)
            rows = []
            for strat in (CurtailAbsorb(), DayAheadOnly(model), RollingRT(model)):
                r = backtest(strat, model, asset, days)
                rows.append({
                    "strategy": r["strategy"], "label": r["label"],
                    "annual_won": r["annual_won"], "margin_per_kwh": r["margin_per_kwh"],
                    "free_share": r["free_share"], "hit_rate": r["hit_rate"],
                })
            out.append({"site": site, "behind_meter": bm,
                        "price_basis": "계시별 요금(TOU)" if bm else "시장 실시간가",
                        "rows": rows})
        return success_response({
            "sites": out,
            "insight": (
                "계량기 안쪽 자산은 공짜 충전 비중이 항상 0%다 — 도매가가 0원이어도 "
                "소매 요금을 내기 때문이다. 반대로 요금제는 미리 확정돼 있어 "
                "실시간 재계획의 가치가 거의 없다. 실시간 반응은 시장 자산에서만 값이 나온다."
            ),
        })
    except Exception as exc:  # noqa: BLE001
        logger.error("jeju_site_compare_failed", error=str(exc))
        return success_response({"sites": []})


@router.get("/jeju/sensitivity")
async def jeju_sensitivity(days: int = 180) -> dict:
    """출력제어 빈도 민감도 — 사업 성립 조건을 숫자로 드러낸다.

    이 사업의 수익은 전략의 정교함이 아니라 **제주에 버려지는 전력이 얼마나 있는가**로
    거의 결정된다. 그 사실을 숨기지 않고 화면에 그대로 띄운다.
    """
    try:
        from app.services.strategies.jeju import (
            Asset, CurtailAbsorb, JejuMarketModel, backtest,
        )

        rows = []
        for label, mr in [("출력제어 없음", 0.0), ("드묾", 200.0),
                          ("보통", 350.0), ("잦음", 450.0)]:
            r = backtest(CurtailAbsorb(mr),
                         JejuMarketModel(spread_scale=0.41, must_run_mw=mr),
                         Asset(), days)
            rows.append({
                "scenario": label,
                "must_run_mw": mr,
                "free_share": r["free_share"],
                "charge_unit_won": round(r["charge_cost_won"] / max(r["charge_kwh"], 1), 1),
                "margin_per_kwh": r["margin_per_kwh"],
                "annual_won": r["annual_won"],
            })
        return success_response({
            "rows": rows,
            "inland_reference": {
                "label": "육지 실측 (2024~, 300일 표본)",
                "charge_unit_won": 42.5, "peak_won": 90.1,
                "var_cost_won": 97.2, "margin_per_kwh": -7.1,
            },
            "verdict": (
                "출력제어가 없으면 제주에서도 마진은 +4원/kWh 수준으로 사실상 사업이 안 된다. "
                "수익의 원천은 가격 예측 정확도가 아니라 '버려지는 전력에 접근할 수 있는가'다."
            ),
        })
    except Exception as exc:  # noqa: BLE001
        logger.error("jeju_sensitivity_failed", error=str(exc))
        return success_response({"rows": []})


@router.post("/smp-api/refresh")
async def smp_api_refresh(force: bool = False) -> dict:
    """KPX 하루전 SMP·수요예측 갱신 — **하루 1회만 호출**.

    일일 트래픽이 100회뿐이라 스트림 경로에서는 절대 부르지 않는다.
    운영자가 아침에 한 번 누르거나 스케줄러가 하루 1회 호출한다.
    """
    try:
        from app.services.kpx_smp_api import smp_api

        curve = await smp_api.refresh(force=force)
        st = smp_api.status()
        return success_response({
            "status": st,
            "smp": curve.get("smp"),
            "demand": curve.get("demand"),
            "ok": bool(curve.get("smp")),
        })
    except Exception as exc:  # noqa: BLE001
        logger.error("smp_api_refresh_failed", error=str(exc))
        return success_response({"ok": False})


@router.post("/smp-api/inject")
async def smp_api_inject(payload: dict) -> dict:
    """국내에서 받아 온 KPX 응답을 그대로 주입한다.

    data.go.kr은 해외 IP에서 접속이 막히는 경우가 있어, 해외에 있는 배포 서버가
    직접 호출하지 못한다(ConnectTimeout). 그럴 때 국내 PC에서 받은 원본 JSON을
    이 경로로 밀어 넣으면 **직접 호출과 동일한 파서·캐시**를 타므로 결과는 같다.

    사용:
        scripts/fetch_smp_local.py 실행 (국내 PC)
    """
    try:
        from app.services.kpx_smp_api import smp_api

        return success_response(smp_api.inject(payload))
    except Exception as exc:  # noqa: BLE001
        logger.error("smp_api_inject_failed", error=str(exc))
        return success_response({"ok": False, "error": str(exc)[:200]})


@router.get("/smp-api/status")
async def smp_api_status() -> dict:
    """호출 잔여량·캐시 상태 (호출 없음)."""
    try:
        from app.services.kpx_smp_api import smp_api

        st = smp_api.status()
        st["smp"] = smp_api.smp_curve()
        st["demand"] = smp_api.demand_curve()
        return success_response(st)
    except Exception as exc:  # noqa: BLE001
        logger.error("smp_api_status_failed", error=str(exc))
        return success_response({"enabled": False})


@router.get("/data-source")
async def data_source() -> dict:
    """가격 데이터 출처 — KPX 실데이터 연동 상태."""
    try:
        from app.services.kpx_feed import kpx_feed

        st = kpx_feed.status()
        smp = await kpx_feed.smp_today()
        st["smp_today"] = smp
        st["hint"] = (
            "KPX 실데이터로 운영 중" if st["source"] == "kpx"
            else "KPX_API_KEY 미설정 — 10년 재생 데이터로 운영 중 (공공데이터포털에서 발급)"
        )
        return success_response(st)
    except Exception as exc:  # noqa: BLE001
        logger.error("market_data_source_failed", error=str(exc))
        return success_response({"source": "replay", "label": "재생 데이터"})


@router.get("/history")
async def get_history() -> dict:
    """과거 입찰 세션 이력."""
    try:
        return success_response({"sessions": market_service.history()})
    except Exception as exc:
        logger.error("market_history_failed", error=str(exc))
        return success_response({"sessions": []})


# ── 실시간 시장 (RT, 15분 슬롯) — A1+d ─────────────────────

from datetime import datetime, timedelta, timezone as _tz

_KST = _tz(timedelta(hours=9))


def _rt_slot() -> dict:
    """현재 15분 슬롯 정보 + RT 가격 (DAM MCP 기반 ± 실시간 변동)."""
    import math
    import random as _r
    now = datetime.now(_KST)
    slot_idx = now.hour * 4 + now.minute // 15
    slot_start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    slot_end = slot_start + timedelta(minutes=15)
    base = market_service.mcp_forecast()[now.hour]
    rng = _r.Random(now.toordinal() * 100 + slot_idx)
    rt_price = round(base * (1.0 + rng.uniform(-0.12, 0.18)) *
                     (1.05 + 0.05 * math.sin(slot_idx / 96 * 6.28)), 1)
    return {
        "slot": f"{slot_start.strftime('%H:%M')}~{slot_end.strftime('%H:%M')}",
        "seconds_left": int((slot_end - now).total_seconds()),
        "rt_price": rt_price,
        "dam_ref": round(base, 1),
    }


@router.get("/rt")
async def get_rt_market() -> dict:
    """실시간 시장 현재 슬롯 (15분) — RT 가격, 마감 카운트다운."""
    try:
        return success_response(_rt_slot())
    except Exception as exc:
        logger.error("market_rt_failed", error=str(exc))
        return success_response({"slot": "--", "seconds_left": 0, "rt_price": 0, "dam_ref": 0})


class RtSellRequest(BaseModel):
    qty_kw: float = Field(gt=0, le=500)


@router.post("/rt/sell")
async def rt_sell(body: RtSellRequest) -> dict:
    """RT 즉시 판매 — 현재 슬롯 가격 97%(시장가 주문 슬리피지)로 체결."""
    try:
        from app.core.resources import total_max_discharge_kw
        from app.services.vpp_ledger import vpp_ledger

        slot = _rt_slot()
        qty = min(body.qty_kw, total_max_discharge_kw())
        fill = round(slot["rt_price"] * 0.97, 1)
        kwh = round(qty * 0.25, 1)          # 15분 슬롯 = 0.25h
        revenue = round(kwh * fill, 0)
        vpp_ledger.record(
            "RT판매",
            f"실시간 {slot['slot']} — {qty:.0f}kW×15분 @₩{fill}",
            kwh, revenue,
        )
        ops_service.audit("operator", "RT_SELL", f"{slot['slot']} {qty:.0f}kW 체결 ₩{int(revenue):,}")
        return success_response(
            {"filled": True, "slot": slot["slot"], "qty_kw": qty,
             "fill_price": fill, "kwh": kwh, "revenue": revenue}
        )
    except Exception as exc:
        logger.error("market_rt_sell_failed", error=str(exc))
        return success_response({"filled": False})

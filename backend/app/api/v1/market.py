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
async def get_strategy_bids(strategy: str | None = None) -> dict:
    """활성(또는 지정) 전략의 추천 입찰 곡선.

    /ai-bids 가 학습 정책 전용이라면, 이쪽은 전략 라이브러리 전체를 대상으로 한다.
    """
    try:
        forecast = market_service.mcp_forecast()
        return success_response(strategy_service.build_bids(forecast, strategy=strategy))
    except Exception as exc:
        logger.error("strategy_bids_failed", error=str(exc))
        return success_response({"bids": []})


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


@router.get("/jeju/leaderboard")
async def jeju_leaderboard(days: int = 365, spread_scale: float = 0.41) -> dict:
    """제주 실시간시장 전략 리더보드.

    spread_scale — 일중 변동폭 가정 배율. 0.41이면 육지 실측과 같은 수준의
    스프레드를 가정한 보수적 시나리오다 (제주 RT는 이보다 클 가능성이 높다).
    """
    try:
        from app.services.strategies.jeju import JejuMarketModel, leaderboard as jlb

        return success_response(
            jlb(days=days, model=JejuMarketModel(spread_scale=spread_scale))
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("jeju_leaderboard_failed", error=str(exc))
        return success_response({"leaderboard": []})


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

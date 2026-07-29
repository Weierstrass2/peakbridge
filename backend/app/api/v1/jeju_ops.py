"""제주 운영 시뮬레이터 API — 플러스DR 발령에 대응해 보는 조작 화면용.

시연 흐름:
    1. POST /jeju-ops/event      플러스DR 발령
    2. GET  /jeju-ops/plan       배분 계획 미리보기 (실행 전)
    3. GET  /jeju-ops/compare    균등 배분 vs 피크 여유 기반 대조   ← 핵심
    4. POST /jeju-ops/dispatch   실제 급전 실행
    5. POST /jeju-ops/advance    한 시간 진행

상태는 메모리에만 둔다(서버 재시작 시 초기화).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.schemas.response import success_response
from app.services.jeju_sim import jeju_sim
from app.services.ops_service import ops_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/jeju-ops", tags=["jeju-ops"])


@router.get("/state")
async def get_state() -> dict:
    """현재 시뮬레이터 상태 — 단지 목록·발령 여부·로그."""
    try:
        return success_response(jeju_sim.state())
    except Exception as exc:  # noqa: BLE001
        logger.error("jeju_ops_state_failed", error=str(exc))
        return success_response({"sites": [], "event": None})


class EventReq(BaseModel):
    hour: int | None = Field(default=None, ge=0, le=23,
                             description="발령 시각. 미지정이면 실측 분포에서 추출")
    request_mwh: float | None = Field(default=None, gt=0, le=100,
                                      description="요청 증대량. 미지정이면 실측 평균 기준")


@router.post("/event")
async def raise_event(body: EventReq | None = None) -> dict:
    """플러스DR 발령 — 전력거래소가 '전기를 더 써달라'고 요청한 상황."""
    try:
        b = body or EventReq()
        st = jeju_sim.raise_event(hour=b.hour, request_mwh=b.request_mwh)
        ev = st.get("event") or {}
        ops_service.alarm(
            "WARN", "jeju",
            f"플러스DR 발령 — {ev.get('hour')}시 · 요청 {ev.get('request_kwh', 0):,}kWh",
        )
        return success_response(st)
    except Exception as exc:  # noqa: BLE001
        logger.error("jeju_ops_event_failed", error=str(exc))
        return success_response({"error": str(exc)[:200]})


@router.get("/plan")
async def get_plan(mode: str = "peak") -> dict:
    """배분 계획 미리보기 — 실행하지 않고 어디에 얼마나 걸릴지만 계산."""
    try:
        return success_response(jeju_sim.plan(mode))
    except Exception as exc:  # noqa: BLE001
        logger.error("jeju_ops_plan_failed", error=str(exc))
        return success_response({"error": str(exc)[:200]})


@router.get("/compare")
async def compare(incentive: float = 120.0) -> dict:
    """균등 배분 vs 피크 여유 기반 — 같은 이벤트를 두 방식으로 대조한다.

    이 화면이 우리 소프트웨어의 존재 이유를 숫자로 보여준다.
    이행률은 둘 다 높게 나오지만, 계량기 피크를 올리느냐로 손익이 갈린다.
    """
    try:
        return success_response(jeju_sim.compare(incentive))
    except Exception as exc:  # noqa: BLE001
        logger.error("jeju_ops_compare_failed", error=str(exc))
        return success_response({"error": str(exc)[:200]})


class DispatchReq(BaseModel):
    mode: str = Field(default="peak", description="peak(피크 여유 기반) | even(균등)")
    incentive: float = Field(default=120.0, ge=0, le=1000,
                             description="정산 단가 가정값 (₩/kWh)")


@router.post("/dispatch")
async def dispatch(body: DispatchReq | None = None) -> dict:
    """급전 실행 — 실제로 충전 지시를 내리고 결과를 정산한다."""
    try:
        b = body or DispatchReq()
        r = jeju_sim.dispatch(b.mode, b.incentive)
        if "error" not in r:
            ops_service.audit(
                "operator", "JEJU_DISPATCH",
                f"{b.mode} 배분 · 이행 {r['delivery_rate'] * 100:.0f}% · 순손익 ₩{r['net_won']:,}",
            )
        return success_response(r)
    except Exception as exc:  # noqa: BLE001
        logger.error("jeju_ops_dispatch_failed", error=str(exc))
        return success_response({"error": str(exc)[:200]})


@router.post("/advance")
async def advance() -> dict:
    """한 시간 진행 — 부하가 바뀌고 배터리가 자연 소모된다."""
    try:
        return success_response(jeju_sim.advance())
    except Exception as exc:  # noqa: BLE001
        logger.error("jeju_ops_advance_failed", error=str(exc))
        return success_response({})


@router.post("/reset")
async def reset(sites: int = 12) -> dict:
    """시뮬레이터 초기화."""
    try:
        return success_response(jeju_sim.reset(sites))
    except Exception as exc:  # noqa: BLE001
        logger.error("jeju_ops_reset_failed", error=str(exc))
        return success_response({})

"""
전력시장 시뮬레이션 엔진 — 하루 전 시장(DAM) 입찰·개찰·낙찰.

KPX 육지 SMP의 시간대 패턴(계시별 요금 기반 형상 + 확률 변동)으로
시장청산가격(MCP)을 생성하고, 입찰가 <= MCP면 낙찰(pay-as-clear).
입찰 AI(A3)의 강화학습 환경으로도 재사용된다.
"""

from __future__ import annotations

import math
import random
import uuid
from datetime import datetime, timedelta, timezone

import structlog

from app.ml.energy_optimizer import EnergyOptimizer

logger = structlog.get_logger(__name__)

KST = timezone(timedelta(hours=9))
DAM_DEADLINE_HOUR = 10  # KPX 하루 전 시장 마감 10:00

optimizer = EnergyOptimizer()


def _mcp_curve(day: datetime, jitter: float = 1.0) -> list[float]:
    """시간대별 시장청산가격(₩/kWh) — 요금표 형상 × 확률 변동."""
    prices: list[float] = []
    seed = day.toordinal()
    rng = random.Random(seed)
    daily_level = 1.0 + rng.uniform(-0.08, 0.12)  # 그날의 수급 상황
    for h in range(24):
        base = float(optimizer.get_current_rate(day.replace(hour=h, minute=0))["rate"])
        shape = 1.0 + 0.10 * math.sin((h - 14) / 24 * 2 * math.pi)
        noise = 1.0 + rng.uniform(-0.05, 0.05) * jitter
        prices.append(round(base * 1.15 * daily_level * shape * noise, 1))
    return prices


class MarketService:
    """DAM 입찰 세션 관리 (in-memory)."""

    def __init__(self) -> None:
        self._session: dict | None = None
        self._history: list[dict] = []

    # ── 세션 ─────────────────────────────────────────
    def _new_session(self) -> dict:
        now = datetime.now(KST)
        delivery = (now + timedelta(days=1)).date()
        return {
            "session_id": str(uuid.uuid4())[:8],
            "delivery_date": delivery.isoformat(),
            "status": "draft",           # draft → submitted → cleared
            "bids": [
                {"hour": h, "qty_kw": 0.0, "price": 0.0}
                for h in range(24)
            ],
            "submitted_at": None,
            "cleared_at": None,
            "results": None,
        }

    def get_session(self) -> dict:
        if self._session is None:
            self._session = self._new_session()
        now = datetime.now(KST)
        deadline = now.replace(hour=DAM_DEADLINE_HOUR, minute=0, second=0, microsecond=0)
        if now >= deadline:
            deadline += timedelta(days=1)
        return {
            **self._session,
            "deadline": deadline.isoformat(),
            "seconds_to_deadline": int((deadline - now).total_seconds()),
        }

    def save_bids(self, bids: list[dict]) -> dict:
        s = self._session or self._new_session()
        if s["status"] == "cleared":
            s = self._new_session()  # 개찰 끝난 세션이면 새 세션
        merged = {b["hour"]: b for b in s["bids"]}
        for b in bids:
            h = int(b.get("hour", -1))
            if 0 <= h <= 23:
                merged[h] = {
                    "hour": h,
                    "qty_kw": max(0.0, min(500.0, float(b.get("qty_kw", 0)))),
                    "price": max(0.0, min(500.0, float(b.get("price", 0)))),
                }
        s["bids"] = [merged[h] for h in range(24)]
        s["status"] = "draft"
        self._session = s
        return self.get_session()

    def submit(self) -> dict:
        s = self._session or self._new_session()
        s["status"] = "submitted"
        s["submitted_at"] = datetime.now(KST).isoformat()
        self._session = s
        logger.info("market_bids_submitted", session=s["session_id"])
        return self.get_session()

    # ── 개찰 ─────────────────────────────────────────
    def clear(self) -> dict:
        """개찰 — MCP 생성 후 낙찰 판정 (pay-as-clear 정산 예상)."""
        s = self._session or self._new_session()
        delivery = datetime.fromisoformat(s["delivery_date"] + "T00:00:00")
        mcp = _mcp_curve(delivery)

        results = []
        total_award_kwh = 0.0
        total_revenue = 0.0
        for b in s["bids"]:
            h = b["hour"]
            awarded = b["qty_kw"] > 0 and b["price"] <= mcp[h]
            revenue = round(b["qty_kw"] * mcp[h], 0) if awarded else 0.0
            if awarded:
                total_award_kwh += b["qty_kw"]  # 1시간 공급 기준 kWh
                total_revenue += revenue
            results.append(
                {
                    "hour": h,
                    "qty_kw": b["qty_kw"],
                    "bid_price": b["price"],
                    "mcp": mcp[h],
                    "awarded": awarded,
                    "expected_revenue": revenue,
                }
            )

        s["status"] = "cleared"
        s["cleared_at"] = datetime.now(KST).isoformat()
        s["results"] = {
            "hours": results,
            "awarded_hours": sum(1 for r in results if r["awarded"]),
            "total_award_kwh": round(total_award_kwh, 1),
            "total_expected_revenue": round(total_revenue, 0),
            "avg_mcp": round(sum(mcp) / 24, 1),
        }
        self._session = s
        self._history.insert(0, {k: v for k, v in s.items()})
        self._history = self._history[:30]
        logger.info(
            "market_cleared",
            session=s["session_id"],
            awarded=s["results"]["awarded_hours"],
            revenue=s["results"]["total_expected_revenue"],
        )
        return self.get_session()

    def mcp_forecast(self) -> list[float]:
        """내일 MCP 예상 곡선 (입찰 참고용 — 실제 개찰과 동일 시드)."""
        s = self.get_session()
        delivery = datetime.fromisoformat(s["delivery_date"] + "T00:00:00")
        return _mcp_curve(delivery, jitter=0.0)

    def history(self, limit: int = 10) -> list[dict]:
        return self._history[:limit]


market_service = MarketService()

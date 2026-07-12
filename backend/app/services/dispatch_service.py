"""
급전 이행 엔진 — 낙찰 스케줄 → 급전지시 → 이행률·정산·위약.

Mock RTU: 4초 주기 하트비트 워커가 현장 상태(출력·SOC)를 갱신·기록
(실제 KPX ICCP/RTU 통신 주기 모사). 시연 가속: 기본 60× (1분 = 시장 1시간).
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import structlog

from app.core.resources import MARKET_RULES, ess_resources
from app.services.market_service import market_service
from app.services.vpp_ledger import vpp_ledger

logger = structlog.get_logger(__name__)

KST = timezone(timedelta(hours=9))
RTU_INTERVAL_S = 4.0        # Mock RTU 하트비트 주기
TIME_SCALE = 60.0           # 시연 가속 배율 (60× → 1분 = 1시장시간)


class DispatchService:
    """낙찰 스케줄 이행 상태머신 + Mock RTU 워커."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._active: dict | None = None      # 활성 급전 스케줄
        self._rtu = {"seq": 0, "last_beat": None, "interval_s": RTU_INTERVAL_S}
        # 내부 SOC 모델 (레지스트리 시드, live 자원은 스트림이 갱신한다고 가정)
        self._soc = {k: 60.0 for k in ess_resources()}
        self._soc["building-A"] = 25.0
        self._last_tick: float | None = None

    # ── 스케줄 활성화 ─────────────────────────────────
    def activate_latest_award(self) -> dict | None:
        """가장 최근 개찰 세션을 이행 스케줄로 활성화 (시연 트리거)."""
        hist = market_service.history(1)
        if not hist or not hist[0].get("results"):
            return None
        s = hist[0]
        hours = [
            {
                **r,
                "delivered_kwh": 0.0,
                "status": "대기",         # 대기 → 이행중 → 완료/부족
                "settled": False,
            }
            for r in s["results"]["hours"]
        ]
        self._active = {
            "session_id": s["session_id"],
            "delivery_date": s["delivery_date"],
            "started_at": time.time(),
            "time_scale": TIME_SCALE,
            "hours": hours,
            "penalties": 0.0,
            "energy_revenue": 0.0,
            "cp_revenue": s["results"].get("total_cp_payment", 0.0),
        }
        if self._active["cp_revenue"] > 0:
            vpp_ledger.record(
                "CP정산",
                f"용량요금 — 신고용량 기준 (세션 {s['session_id']})",
                0.0,
                self._active["cp_revenue"],
                event_id=s["session_id"],
            )
        logger.info("dispatch_activated", session=s["session_id"])
        return self.status()

    # ── Mock RTU 워커 ────────────────────────────────
    async def _worker(self) -> None:
        while True:
            try:
                self._tick()
            except Exception as exc:
                logger.warning("dispatch_tick_failed", error=str(exc))
            await asyncio.sleep(RTU_INTERVAL_S)

    def ensure_worker(self) -> None:
        if self._task is None or self._task.done():
            try:
                self._task = asyncio.get_event_loop().create_task(self._worker())
                logger.info("rtu_worker_started", interval_s=RTU_INTERVAL_S)
            except RuntimeError:
                pass

    def _tick(self) -> None:
        now = time.time()
        dt_real = (now - self._last_tick) if self._last_tick else RTU_INTERVAL_S
        dt_real = max(0.05, min(dt_real, RTU_INTERVAL_S * 3))
        self._last_tick = now
        self._rtu["seq"] += 1
        self._rtu["last_beat"] = datetime.now(KST).isoformat()
        a = self._active
        if not a:
            return
        dt_market_h = dt_real * a["time_scale"] / 3600.0  # 이번 틱의 시장시간(h)

        # 가속 시계: 경과 실초 × 배율 → 시장시간
        sim_hours = (time.time() - a["started_at"]) * a["time_scale"] / 3600.0
        current_h = int(sim_hours)
        frac = sim_hours - current_h
        total_cap = sum(r["max_discharge_kw"] for r in ess_resources().values())

        for h in a["hours"]:
            if h["hour"] < current_h and not h["settled"] and h["awarded"]:
                self._settle_hour(h)                       # 지난 구간 정산
            elif h["hour"] == current_h and h["awarded"]:
                h["status"] = "이행중"
                # 자원 배분 비례 방전 + SOC 차감
                target = h["qty_kw"]
                deliverable = 0.0
                for rid, r in ess_resources().items():
                    share = target * (r["max_discharge_kw"] / total_cap)
                    if self._soc[rid] > r["soc_min"]:
                        deliverable += min(share, r["max_discharge_kw"])
                        drain = share * dt_market_h
                        self._soc[rid] = max(
                            r["soc_min"] - 1,
                            self._soc[rid] - drain / r["capacity_kwh"] * 100.0,
                        )
                h["delivered_kwh"] = round(
                    min(h["qty_kw"], h["delivered_kwh"] + deliverable * dt_market_h),
                    2,
                )
                h["progress"] = round(frac * 100)

    def _settle_hour(self, h: dict) -> None:
        h["settled"] = True
        shortfall = max(0.0, h["qty_kw"] - h["delivered_kwh"])
        compliance = (h["delivered_kwh"] / h["qty_kw"] * 100.0) if h["qty_kw"] > 0 else 100.0
        h["compliance"] = round(compliance, 1)
        energy = round(h["delivered_kwh"] * h["mcp"], 0)
        h["status"] = "완료" if compliance >= 97.0 else "부족"
        a = self._active
        if a is None:
            return
        a["energy_revenue"] += energy
        if energy > 0:
            vpp_ledger.record(
                "급전정산",
                f"{h['hour']:02d}시 구간 — {h['delivered_kwh']}kWh @MCP {h['mcp']}원 (이행 {h['compliance']}%)",
                h["delivered_kwh"],
                energy,
            )
        if shortfall > 0.5:
            penalty = round(shortfall * h["mcp"] * MARKET_RULES["penalty_factor"], 0)
            a["penalties"] += penalty
            vpp_ledger.record(
                "위약금",
                f"{h['hour']:02d}시 미이행 {shortfall:.1f}kWh × MCP {h['mcp']} × {MARKET_RULES['penalty_factor']}",
                -shortfall,
                -penalty,
            )
            logger.warning("dispatch_penalty", hour=h["hour"], penalty=penalty)
            try:
                from app.services.ops_service import ops_service
                ops_service.alarm(
                    "CRIT", "dispatch",
                    f"{h['hour']:02d}시 미이행 위약 ₩{int(penalty):,} (이행 {h['compliance']}%)",
                )
            except Exception:
                pass

    # ── 조회 ─────────────────────────────────────────
    def status(self) -> dict:
        self.ensure_worker()
        a = self._active
        base = {
            "rtu": self._rtu,
            "soc": {k: round(v, 1) for k, v in self._soc.items()},
            "market_types": [
                {"id": "DAM", "name": "하루 전 시장", "state": "운영"},
                {"id": "RT", "name": "실시간 시장", "state": "예정"},
                {"id": "AS", "name": "보조서비스(FR)", "state": "예정"},  # A1+j 슬롯
            ],
        }
        if not a:
            return {**base, "active": None}
        sim_hours = (time.time() - a["started_at"]) * a["time_scale"] / 3600.0
        awarded = [h for h in a["hours"] if h["awarded"]]
        awarded_kwh = sum(h["qty_kw"] for h in awarded)
        delivered_kwh = sum(h["delivered_kwh"] for h in awarded)
        defended = sum(
            h["delivered_kwh"] * h["mcp"] * 1.2 for h in awarded if h["delivered_kwh"] > 0
        )
        return {
            **base,
            "active": {
                "session_id": a["session_id"],
                "delivery_date": a["delivery_date"],
                "time_scale": a["time_scale"],
                "sim_clock": f"{int(sim_hours) % 24:02d}:{int((sim_hours % 1) * 60):02d}",
                "hours": a["hours"],
                "awarded_hours": len(awarded),
                "settled_hours": sum(1 for h in awarded if h["settled"]),
                "cumulative": {
                    "awarded_kwh": round(awarded_kwh, 1),
                    "delivered_kwh": round(delivered_kwh, 1),
                    "rate": round(delivered_kwh / awarded_kwh * 100, 1) if awarded_kwh > 0 else 100.0,
                    "defended_won": round(defended, 0),
                },
                "energy_revenue": round(a["energy_revenue"], 0),
                "cp_revenue": round(a["cp_revenue"], 0),
                "penalties": round(a["penalties"], 0),
                "net": round(a["energy_revenue"] + a["cp_revenue"] - a["penalties"], 0),
            },
        }


dispatch_service = DispatchService()

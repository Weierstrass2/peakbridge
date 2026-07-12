"""운영 센터 — 알람 큐(ACK), 감사 로그, 이행 리스크 판정. (in-memory)"""
from __future__ import annotations
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
import structlog

logger = structlog.get_logger(__name__)
KST = timezone(timedelta(hours=9))
_now = lambda: datetime.now(KST).isoformat()


class OpsService:
    def __init__(self) -> None:
        self._alarms: deque[dict] = deque(maxlen=100)
        self._audit: deque[dict] = deque(maxlen=200)

    # ── 알람 (B1) ──────────────────────────────
    def alarm(self, severity: str, source: str, msg: str) -> None:
        # 60초 내 동일 메시지 중복 억제
        for a in list(self._alarms)[:10]:
            if a["msg"] == msg and not a["ack"]:
                return
        self._alarms.appendleft({
            "id": str(uuid.uuid4())[:8], "ts": _now(),
            "severity": severity, "source": source, "msg": msg, "ack": False,
        })
        logger.info("ops_alarm", severity=severity, source=source, msg=msg)

    def ack(self, alarm_id: str) -> bool:
        for a in self._alarms:
            if a["id"] == alarm_id:
                a["ack"] = True
                a["ack_ts"] = _now()
                self.audit("operator", "ALARM_ACK", f"{alarm_id} 확인")
                return True
        return False

    def alarms(self, limit: int = 30) -> dict:
        items = list(self._alarms)[:limit]
        return {
            "unack": sum(1 for a in self._alarms if not a["ack"]),
            "items": items,
        }

    # ── 감사 로그 (B4) ─────────────────────────
    def audit(self, actor: str, action: str, detail: str) -> None:
        self._audit.appendleft({
            "ts": _now(), "actor": actor, "action": action, "detail": detail,
        })

    def audits(self, limit: int = 50) -> list[dict]:
        return list(self._audit)[:limit]

    # ── 이행 리스크 (B2) ───────────────────────
    def risk(self) -> dict:
        from app.core.resources import ess_resources
        from app.services.dispatch_service import dispatch_service

        res = ess_resources()
        soc = dispatch_service._soc
        usable = sum(
            max(0.0, (soc.get(k, 60.0) - r["soc_min"])) / 100 * r["capacity_kwh"]
            for k, r in res.items()
        )
        a = dispatch_service._active
        obligation = 0.0
        if a:
            obligation = sum(
                h["qty_kw"] - h["delivered_kwh"]
                for h in a["hours"]
                if h["awarded"] and not h["settled"]
            )
        if obligation <= 0:
            status, ratio = "안전", 1.0
        else:
            ratio = usable / obligation
            status = "안전" if ratio >= 1.05 else "주의" if ratio >= 0.7 else "위험"
        if status == "위험":
            self.alarm("CRIT", "dispatch", f"이행 불가 위험 — 가용 {usable:.0f}kWh < 의무 {obligation:.0f}kWh")
        elif status == "주의":
            self.alarm("WARN", "dispatch", f"이행 여유 부족 — 가용 {usable:.0f}kWh / 의무 {obligation:.0f}kWh")
        return {
            "status": status,
            "usable_kwh": round(usable, 1),
            "obligation_kwh": round(obligation, 1),
            "coverage": round(min(ratio, 9.99), 2),
        }


ops_service = OpsService()

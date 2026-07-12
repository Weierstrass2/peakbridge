"""VPP 거래 장부 — 수요반응 정산·차익거래 기록 (in-memory 원장)."""

from __future__ import annotations

import uuid
from collections import deque
from datetime import datetime, timezone, timedelta

import structlog

logger = structlog.get_logger(__name__)

KST = timezone(timedelta(hours=9))


class VPPLedger:
    """DR 정산 / 차익거래 수익 원장."""

    def __init__(self) -> None:
        self._entries: deque[dict] = deque(maxlen=200)

    def record(
        self,
        entry_type: str,      # "DR정산" | "차익거래"
        detail: str,
        kwh: float,
        revenue: float,
        event_id: str | None = None,
    ) -> dict:
        entry = {
            "id": str(uuid.uuid4())[:8],
            "type": entry_type,
            "detail": detail,
            "kwh": round(kwh, 1),
            "revenue": round(revenue, 0),
            "event_id": event_id,
            "ts": datetime.now(KST).isoformat(),
        }
        self._entries.appendleft(entry)
        logger.info("ledger_recorded", **{k: v for k, v in entry.items() if k != "detail"})
        return entry

    def summary(self) -> dict:
        today = datetime.now(KST).date().isoformat()
        today_entries = [e for e in self._entries if e["ts"][:10] == today]
        by_type: dict[str, float] = {}
        for e in self._entries:
            by_type[e["type"]] = by_type.get(e["type"], 0.0) + e["revenue"]
        return {
            "by_type": {k: round(v, 0) for k, v in by_type.items()},
            "today_trades": len(today_entries),
            "today_kwh": round(sum(e["kwh"] for e in today_entries), 1),
            "today_revenue": round(sum(e["revenue"] for e in today_entries), 0),
            "total_revenue": round(sum(e["revenue"] for e in self._entries), 0),
        }

    def entries(self, limit: int = 20) -> list[dict]:
        return list(self._entries)[: max(1, min(200, limit))]


vpp_ledger = VPPLedger()

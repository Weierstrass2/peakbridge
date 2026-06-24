"""알림 API — 조회 및 해결."""

import uuid

from fastapi import APIRouter

from app.core.deps import DbSession
from app.core.exceptions import NotFoundError
from app.repositories.alert_repository import AlertRepository
from app.schemas.response import success_response

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/{building_id}")
async def list_alerts(session: DbSession, building_id: str) -> dict:
    """GET /api/v1/alerts/{building_id} — 최근 50개 알림."""
    repo = AlertRepository(session)
    alerts = await repo.list_recent(building_id, limit=50)
    return success_response(
        [
            {
                "id": str(a.id),
                "building_id": a.building_id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "grid_current": a.grid_current,
                "ess_soc": a.ess_soc,
                "reduction_percent": a.reduction_percent,
                "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
                "created_at": a.created_at.isoformat(),
            }
            for a in alerts
        ]
    )


@router.post("/{alert_id}/resolve")
async def resolve_alert(session: DbSession, alert_id: uuid.UUID) -> dict:
    """POST /api/v1/alerts/{alert_id}/resolve — 알림 해결."""
    repo = AlertRepository(session)
    alert = await repo.resolve(alert_id)
    if not alert:
        raise NotFoundError("Alert", str(alert_id))
    return success_response(
        {
            "id": str(alert.id),
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        }
    )

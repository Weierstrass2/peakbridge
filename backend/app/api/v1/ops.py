"""운영 센터 API — 알람 큐·감사 로그·이행 리스크."""
from __future__ import annotations
import structlog
from fastapi import APIRouter, Query
from app.schemas.response import success_response
from app.services.ops_service import ops_service

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/alarms")
async def get_alarms(limit: int = Query(default=30, ge=1, le=100)) -> dict:
    try:
        return success_response(ops_service.alarms(limit))
    except Exception as exc:
        logger.error("ops_alarms_failed", error=str(exc))
        return success_response({"unack": 0, "items": []})


@router.post("/alarms/{alarm_id}/ack")
async def ack_alarm(alarm_id: str) -> dict:
    try:
        return success_response({"acked": ops_service.ack(alarm_id)})
    except Exception as exc:
        logger.error("ops_ack_failed", error=str(exc))
        return success_response({"acked": False})


@router.get("/audit")
async def get_audit(limit: int = Query(default=50, ge=1, le=200)) -> dict:
    try:
        return success_response({"entries": ops_service.audits(limit)})
    except Exception as exc:
        logger.error("ops_audit_failed", error=str(exc))
        return success_response({"entries": []})


@router.get("/risk")
async def get_risk() -> dict:
    try:
        return success_response(ops_service.risk())
    except Exception as exc:
        logger.error("ops_risk_failed", error=str(exc))
        return success_response({"status": "안전", "usable_kwh": 0, "obligation_kwh": 0, "coverage": 1})

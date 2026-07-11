"""OpenADR/DR API."""

from fastapi import APIRouter, Body

from app.schemas.response import success_response

router = APIRouter()


@router.get("/status")
async def get_dr_status() -> dict:
    """GET /api/v1/dr/status."""
    return success_response(
        {
            "status": "not_implemented",
            "openadr_enabled": False,
            "last_event": None,
        }
    )


@router.post("/event")
async def create_dr_event(body: dict = Body(...)) -> dict:
    """POST /api/v1/dr/event."""
    return success_response(
        {
            "status": "not_implemented",
            "event_created": True,
            "signal_type": body.get("signal_type"),
            "value": body.get("value"),
        }
    )

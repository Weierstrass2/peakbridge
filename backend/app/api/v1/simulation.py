"""시뮬레이션 트리거 API."""

from fastapi import APIRouter, Body

from app.schemas.response import success_response

router = APIRouter()


@router.post("/trigger")
async def trigger_simulation(body: dict = Body(...)) -> dict:
    """POST /api/v1/simulation/trigger."""
    scenario = body.get("scenario", "normal")
    response = {
        "status": "not_implemented",
        "scenario": scenario,
        "message": "기본 simulation placeholder 응답입니다.",
    }

    if scenario == "midnight_charge":
        response.update({"action": "charge"})
    elif scenario == "peak_discharge":
        response.update({"action": "discharge", "grid_current": 18.4})
    elif scenario == "demand_response":
        response.update({"signal_type": "SIMPLE", "signal_value": 3})
    else:
        response.update({"action": "standby"})

    return success_response(response)

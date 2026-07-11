"""배전망 시뮬레이션 API."""

from fastapi import APIRouter, Body

from app.schemas.response import success_response

router = APIRouter()


@router.get("/simulation/{building_id}")
async def get_grid_simulation(building_id: str) -> dict:
    """GET /api/v1/grid/simulation/{building_id}."""
    return success_response(
        {
            "status": "not_implemented",
            "building_id": building_id,
            "transformer_load_percent": 82.0,
            "after_peakbridge_percent": 74.0,
            "status_label": "정상",
        }
    )


@router.post("/simulate")
async def simulate_grid(body: dict = Body(...)) -> dict:
    """POST /api/v1/grid/simulate."""
    return success_response(
        {
            "status": "not_implemented",
            "input": body,
            "transformer_load_percent": 102.2,
            "after_peakbridge_percent": 76.4,
            "peak_reduction_percent": 25.2,
        }
    )

"""VPP 포트폴리오 API."""

from fastapi import APIRouter

from app.schemas.response import success_response

router = APIRouter()


@router.get("/portfolio")
async def get_vpp_portfolio() -> dict:
    """GET /api/v1/vpp/portfolio."""
    return success_response(
        {
            "status": "not_implemented",
            "total_capacity_kwh": 0.0,
            "buildings": [],
        }
    )


@router.get("/revenue/arbitrage")
async def get_vpp_arbitrage_revenue() -> dict:
    """GET /api/v1/vpp/revenue/arbitrage."""
    return success_response(
        {
            "status": "not_implemented",
            "arbitrage_revenue_won": 0.0,
        }
    )

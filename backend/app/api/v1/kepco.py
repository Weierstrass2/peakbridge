"""
한전 전력거래소 API 라우터
"""

from fastapi import APIRouter, Depends
from app.services.kepco_service import KepcoService

router = APIRouter()
kepco_service = KepcoService()


@router.get("/status")
async def get_kepco_status():
    """대시보드용 한전 전체 요약"""
    return await kepco_service.get_kepco_summary()


@router.get("/state")
async def get_kepco_state():
    """RL 에이전트용 상태 수집"""
    return await kepco_service.get_state_data()

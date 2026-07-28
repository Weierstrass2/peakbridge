"""트레이딩 데스크 패키지 — 리스크·애널리틱스·블로터.

    risk.py      한도 체계, 사전 리스크 체크, VaR/CVaR, 스트레스, 킬스위치
    analytics.py 손익 분해, 체결품질(TCA), 예측 품질, 롤링 지표
    desk.py      위 둘을 묶는 운영 서비스 (블로터·세션 기록)
"""

from .analytics import (
    attribute_pnl,
    forecast_quality,
    rolling_metrics,
    transaction_cost_analysis,
)
from .desk import TradingDesk, trading_desk
from .risk import RiskEngine, RiskLimits, RiskState

__all__ = [
    "RiskEngine",
    "RiskLimits",
    "RiskState",
    "attribute_pnl",
    "transaction_cost_analysis",
    "forecast_quality",
    "rolling_metrics",
    "TradingDesk",
    "trading_desk",
]

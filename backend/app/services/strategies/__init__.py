"""VPP 자동매매 전략 · 백테스트 패키지.

퀀트 트레이딩의 구조(전략 라이브러리 → 백테스트 → 성과지표 비교 → 운영 배포)를
전력 도매시장 입찰에 그대로 이식한 모듈이다.

사용:
    python scripts/benchmark_strategies.py            # 전 전략 벤치마크
    from app.services.strategies import registry      # 전략 목록
"""

from .backtest import (
    BacktestResult,
    DayResult,
    MarketSimulator,
    bootstrap_ci,
    run_backtest,
    split_walk_forward,
)
from .base import Bid, MarketContext, Strategy
from .library import registry
from .stochastic import StochasticCVaR, make_scenarios

__all__ = [
    "Bid",
    "MarketContext",
    "Strategy",
    "registry",
    "StochasticCVaR",
    "make_scenarios",
    "MarketSimulator",
    "BacktestResult",
    "DayResult",
    "run_backtest",
    "split_walk_forward",
    "bootstrap_ci",
]

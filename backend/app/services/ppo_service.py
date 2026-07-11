"""
PPO 모델 기반 ESS 제어 추천 서비스.

EV2Gym(충전기 20유닛 환경, 관측 63차원)으로 학습된 best_model.zip을
torch/stable_baselines3 없이 numpy 로더(app.ml.np_policy)로 직접 로드해
deterministic 추론합니다. 로드/추론 실패 시 EnergyOptimizer 폴백 (500 금지).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import structlog

from app.core.config import settings
from app.ml.energy_optimizer import EnergyOptimizer

logger = structlog.get_logger(__name__)

# ── 학습 모델 스펙 (EV2Gym PublicPST) ─────────────────
OBS_DIM = 63          # 관측 차원
N_UNITS = 20          # 충전기(ESS 유닛) 슬롯 수
UNIT_RATED_KW = 22.0  # 유닛 정격 (PublicPST 기준)

# 싱글톤 모델 캐시
_ppo_model = None
_model_loaded = False


def _model_path() -> Path:
    """backend 루트 기준 모델 경로 (cwd 무관)."""
    root = Path(__file__).resolve().parents[2]  # .../backend
    return root / "models" / "best" / "best_model.zip"


def _load_model_once() -> bool:
    """서버 시작 시 1회만 모델 로드 (numpy 로더, torch 불필요)."""
    global _ppo_model, _model_loaded
    if _model_loaded:
        return _ppo_model is not None
    _model_loaded = True

    path = _model_path()
    if not path.exists():
        logger.warning("ppo_model_not_found", path=str(path))
        return False
    try:
        from app.ml.np_policy import NumpyPPOPolicy

        _ppo_model = NumpyPPOPolicy(str(path))
        logger.info(
            "ppo_model_loaded",
            path=str(path),
            layers=[w.shape for w, _ in _ppo_model.pi_layers],
        )
        return True
    except Exception as exc:
        logger.error("ppo_model_load_failed", error=str(exc))
        _ppo_model = None
        return False


class PPOService:
    """PPO 모델 기반 추천 서비스 (63차원 어댑터 포함)."""

    def __init__(self) -> None:
        self.optimizer = EnergyOptimizer()
        _load_model_once()

    # ── 관측 어댑터: 실측값 → 63차원 ──────────────────
    def _get_observation(
        self,
        grid_current: float,
        ess_soc: float,
        current_temp: float,
        tariff_rate: float,
    ) -> np.ndarray:
        """
        실시간 상태를 학습 환경(PublicPST) 관측 형식으로 근사 매핑.

        [0] 하루 진행률, [1] 전력 한도 활용률(전류/임계치),
        [2] 요금 수준(최대부하 대비), 슬롯0 = 실유닛(연결, 부하율, SOC),
        나머지 슬롯 = 미연결(0).
        """
        now = datetime.now()
        threshold = max(0.1, settings.PEAK_THRESHOLD_A)

        obs = np.zeros(OBS_DIM, dtype=np.float32)
        obs[0] = (now.hour * 60 + now.minute) / 1440.0
        obs[1] = min(2.0, max(0.0, grid_current / threshold))
        obs[2] = min(1.5, max(0.0, tariff_rate / 147.0))

        # 슬롯0: 실제 묶음 ESS 유닛 (연결=1, 부하율, SOC)
        base = 3
        obs[base + 0] = 1.0
        obs[base + 1] = min(1.0, max(0.0, grid_current * 0.220 / UNIT_RATED_KW))
        obs[base + 2] = min(1.0, max(0.0, ess_soc / 100.0))
        # 슬롯 1~19: 미연결 유닛 (0 유지) — 학습 시 빈 충전기와 동일 표현

        return obs

    # ── 출력 해석: 연속 20개 → 권고 ───────────────────
    @staticmethod
    def _interpret(outputs: np.ndarray) -> tuple[float, float]:
        """(슬롯0 충전률 0~1, 전체 평균 충전률 0~1)."""
        clipped = np.clip(outputs, 0.0, 1.0)
        return float(clipped[0]), float(clipped.mean())

    async def get_recommendation(
        self,
        building_id: str,
        grid_current: float,
        ess_soc: float,
        current_temp: float,
        tariff_rate: float,
    ) -> dict:
        """PPO 모델 기반 추천 반환, 실패 시 fallback."""
        if _ppo_model is None:
            return self._fallback_recommendation(grid_current, ess_soc)

        try:
            obs = self._get_observation(
                grid_current, ess_soc, current_temp, tariff_rate
            )
            outputs = _ppo_model.predict(obs)
            rate0, rate_mean = self._interpret(np.asarray(outputs))

            threshold = max(0.1, settings.PEAK_THRESHOLD_A)
            hour = datetime.now().hour
            is_night = hour >= 23 or hour < 9

            # 모델 충전률 + 안전 규칙 결합
            if (
                grid_current >= threshold * 0.9
                and ess_soc > settings.ESS_MIN_SOC
                and rate0 <= 0.5
            ):
                action = "discharge"
                reason = (
                    f"PPO 충전 억제 신호(유닛 충전률 {rate0 * 100:.0f}%) "
                    f"+ 그리드 {grid_current:.1f}A 임계 근접 — ESS 방전 권장"
                )
                recommended_rate = round((1.0 - rate0) * 100)
            elif rate0 >= 0.5 and ess_soc < 85:
                action = "charge"
                ctx = "경부하 시간대" if is_night else "여유 구간"
                reason = f"PPO 충전 신호(유닛 충전률 {rate0 * 100:.0f}%) — {ctx} 충전 권장"
                recommended_rate = round(rate0 * 100)
            else:
                action = "standby"
                reason = f"PPO 판단 대기 (유닛 충전률 {rate0 * 100:.0f}%, 평균 {rate_mean * 100:.0f}%)"
                recommended_rate = round(rate0 * 100)

            return {
                "model": "PPO (5M steps)",
                "recommended_rate": max(0, min(100, recommended_rate)),
                "action": action,
                "reason": reason,
                "grid_current": grid_current,
                "ess_soc": ess_soc,
            }
        except Exception as exc:
            logger.error("ppo_predict_failed", error=str(exc))
            return self._fallback_recommendation(grid_current, ess_soc)

    def _fallback_recommendation(self, grid_current: float, ess_soc: float) -> dict:
        """EnergyOptimizer 기반 fallback 추천."""
        rec = self.optimizer.get_realtime_recommendation(
            ess_soc=ess_soc,
            grid_current=grid_current,
            threshold=settings.PEAK_THRESHOLD_A,
        )
        return {
            "model": "fallback",
            "recommended_rate": 70,
            "action": rec["action"],
            "reason": rec["reason"],
            "grid_current": grid_current,
            "ess_soc": ess_soc,
        }

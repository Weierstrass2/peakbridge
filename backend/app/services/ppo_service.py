"""PPO 모델 기반 ESS 제어 추천 서비스."""

from __future__ import annotations

import os
from datetime import datetime

import structlog

from app.core.config import settings
from app.ml.energy_optimizer import EnergyOptimizer

logger = structlog.get_logger(__name__)

# 싱글톤 모델 캐시
_ppo_model = None
_model_loaded = False


def _load_model_once():
    """서버 시작 시 1회만 모델 로드."""
    global _ppo_model, _model_loaded
    if _model_loaded:
        return _ppo_model is not None

    _model_loaded = True
    model_path = os.path.join("models", "best", "best_model.zip")

    if not os.path.exists(model_path):
        logger.warning("ppo_model_not_found", path=model_path)
        return False

    try:
        from stable_baselines3 import PPO
        _ppo_model = PPO.load(model_path)
        logger.info("ppo_model_loaded", path=model_path)
        return True
    except Exception as exc:
        logger.error("ppo_model_load_failed", error=str(exc))
        return False


class PPOService:
    """PPO 모델 기반 추천 서비스."""

    def __init__(self):
        self.optimizer = EnergyOptimizer()
        _load_model_once()

    def _get_observation(
        self,
        grid_current: float,
        ess_soc: float,
        current_temp: float,
        tariff_rate: float,
    ) -> list[float]:
        """관측 벡터 구성."""
        now = datetime.now()
        hour = now.hour
        weekday = now.weekday()
        month = now.month

        # 계절 (0~3)
        if 3 <= month <= 5:
            season = 0  # 봄
        elif 6 <= month <= 8:
            season = 1  # 여름
        elif 9 <= month <= 11:
            season = 2  # 가을
        else:
            season = 3  # 겨울

        # 최대부하 시간대 여부
        is_peak_hour = 1 if (11 <= hour < 13 or 17 <= hour < 21) else 0

        return [
            grid_current,
            ess_soc,
            current_temp,
            tariff_rate,
            hour,
            weekday,
            season,
            is_peak_hour,
        ]

    async def get_recommendation(
        self,
        building_id: str,
        grid_current: float,
        ess_soc: float,
        current_temp: float,
        tariff_rate: float,
    ) -> dict:
        """PPO 모델 기반 추천 반환, 실패시 fallback."""
        if _ppo_model is None:
            return self._fallback_recommendation(grid_current, ess_soc)

        try:
            obs = self._get_observation(
                grid_current, ess_soc, current_temp, tariff_rate
            )
            action, _states = _ppo_model.predict(obs, deterministic=True)

            # action 해석 (0: standby, 1: charge, 2: discharge)
            action_map = {0: "standby", 1: "charge", 2: "discharge"}
            recommended_action = action_map.get(int(action), "standby")

            # 추천율 계산 (간단한 로직)
            recommended_rate = 75
            reason = "PPO 모델 추천"

            if recommended_action == "discharge":
                if grid_current > settings.PEAK_THRESHOLD_A:
                    reason = "피크 시간대 + 높은 그리드 전류"
                    recommended_rate = 90
                else:
                    reason = "PPO 모델 방전 추천"
            elif recommended_action == "charge":
                if 23 <= datetime.now().hour or datetime.now().hour < 9:
                    reason = "경부하 시간대 충전 권장"
                    recommended_rate = 85
                else:
                    reason = "PPO 모델 충전 추천"

            return {
                "model": "PPO (5M steps)",
                "recommended_rate": recommended_rate,
                "action": recommended_action,
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

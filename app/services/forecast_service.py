"""
Prophet 기반 전력 수요 예측 서비스.

모델 학습/예측/임계치 초과 시각 판단.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import SensorType
from app.ml.forecaster import PowerForecaster
from app.repositories.sensor_repository import SensorRepository

logger = structlog.get_logger(__name__)

# building_id → PowerForecaster 캐시
_forecasters: dict[str, PowerForecaster] = {}


class ForecastService:
    """건물별 전력 예측 서비스."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.sensor_repo = SensorRepository(session)

    def _get_forecaster(self, building_id: str) -> PowerForecaster:
        if building_id not in _forecasters:
            _forecasters[building_id] = PowerForecaster(building_id)
        return _forecasters[building_id]

    async def train(self, building_id: str) -> bool:
        """과거 grid_current 데이터로 Prophet 모델 재학습."""
        readings = await self.sensor_repo.get_readings_for_training(
            building_id, SensorType.GRID_CURRENT.value
        )
        data = [
            {"recorded_at": r.recorded_at, "value": r.value} for r in readings
        ]
        forecaster = self._get_forecaster(building_id)
        forecaster.train(data)
        logger.info("forecast_model_trained", building_id=building_id, rows=len(data))
        return True

    async def predict(self, building_id: str) -> list[dict]:
        """향후 60분 예측값 반환."""
        forecaster = self._get_forecaster(building_id)
        if not forecaster.load() and not forecaster._model:
            await self.train(building_id)
        predictions = forecaster.predict_next_hour()
        return [
            {
                "time": p["time"].isoformat()
                if isinstance(p["time"], datetime)
                else p["time"],
                "predicted_current": p["predicted"],
                "lower": p["lower"],
                "upper": p["upper"],
                "will_exceed": p["will_exceed"],
            }
            for p in predictions
        ]

    async def will_exceed_threshold(self, building_id: str) -> datetime | None:
        """피크 예상 시각 — 임계치 초과 예측 시각 반환."""
        predictions = await self.predict(building_id)
        for p in predictions:
            if p["will_exceed"]:
                time_val = p["time"]
                if isinstance(time_val, str):
                    return datetime.fromisoformat(time_val.replace("Z", "+00:00"))
                return time_val
        return None

    async def get_next_hour_summary(self, building_id: str) -> list[dict]:
        """대시보드용 예측 요약."""
        return await self.predict(building_id)

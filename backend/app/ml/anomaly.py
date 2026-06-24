"""
IsolationForest 기반 센서 이상치 감지.

물리적으로 불가능한 값과 통계적 이상 패턴을 필터링합니다.
"""

from __future__ import annotations

import structlog
from sklearn.ensemble import IsolationForest
import numpy as np

logger = structlog.get_logger(__name__)


# 센서 타입별 물리적 유효 범위
PHYSICAL_LIMITS: dict[str, tuple[float, float]] = {
    "grid_current": (0.0, 200.0),
    "ess_soc": (0.0, 100.0),
    "charger_current": (0.0, 80.0),
}


class AnomalyDetector:
    """IsolationForest + 물리적 범위 검증."""

    def __init__(self, sensor_type: str = "grid_current") -> None:
        self.sensor_type = sensor_type
        self._model: IsolationForest | None = None
        self._fitted = False

    def fit(self, readings: list[float]) -> None:
        """과거 측정값으로 IsolationForest 학습."""
        if len(readings) < 20:
            logger.warning("anomaly_detector_insufficient_data", count=len(readings))
            return
        X = np.array(readings).reshape(-1, 1)
        self._model = IsolationForest(
            contamination=0.05,
            random_state=42,
            n_estimators=100,
        )
        self._model.fit(X)
        self._fitted = True
        logger.info("anomaly_detector_fitted", sensor_type=self.sensor_type)

    def detect(self, value: float) -> bool:
        """
        이상치 여부 판단.

        Returns: True = 이상치
        """
        if self.is_sensor_error(value):
            return True
        if not self._fitted or self._model is None:
            return False
        prediction = self._model.predict([[value]])
        return prediction[0] == -1

    def is_sensor_error(self, value: float) -> bool:
        """물리적으로 불가능한 값 필터링."""
        limits = PHYSICAL_LIMITS.get(self.sensor_type, (0.0, 1000.0))
        return value < limits[0] or value > limits[1]

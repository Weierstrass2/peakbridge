"""
Facebook Prophet 기반 전력 수요 예측.

Prophet 사용 불가 시 sklearn 폴백 모델로 대체합니다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import structlog
from sklearn.linear_model import LinearRegression

from app.core.config import settings

logger = structlog.get_logger(__name__)

try:
    from prophet import Prophet
except ImportError:  # pragma: no cover
    Prophet = None  # type: ignore[misc, assignment]


class PowerForecaster:
    """Prophet(또는 폴백) 기반 그리드 전류 예측기."""

    def __init__(self, building_id: str, model_dir: str | None = None) -> None:
        self.building_id = building_id
        self.model_dir = Path(model_dir or settings.ML_MODEL_DIR)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = self.model_dir / f"forecaster_{building_id}.joblib"
        self._model: Any = None
        self.threshold = settings.PEAK_THRESHOLD_A

    def train(self, readings: list[dict]) -> None:
        """과거 측정값으로 모델 학습."""
        df = self._to_prophet_df(readings)
        if len(df) < 10:
            logger.warning("insufficient_data_using_synthetic", building=self.building_id)
            df = self.generate_synthetic_data()

        if Prophet is not None:
            try:
                model = Prophet(
                    daily_seasonality=True,
                    weekly_seasonality=True,
                    yearly_seasonality=False,
                    changepoint_prior_scale=0.05,
                )
                model.add_country_holidays(country_name="KR")
                model.fit(df)
                self._model = {"type": "prophet", "model": model}
                joblib.dump(self._model, self.model_path)
                logger.info("forecaster_trained_prophet", building=self.building_id)
                return
            except Exception as exc:
                logger.warning("prophet_train_failed", error=str(exc))

        self._train_fallback(df)
        joblib.dump(self._model, self.model_path)
        logger.info("forecaster_trained_fallback", building=self.building_id)

    def _train_fallback(self, df: pd.DataFrame) -> None:
        """Prophet 실패 시 sklearn 선형 회귀 폴백."""
        features = pd.DataFrame(
            {
                "hour": df["ds"].dt.hour,
                "minute": df["ds"].dt.minute,
                "weekday": df["ds"].dt.weekday,
                "is_weekend": (df["ds"].dt.weekday >= 5).astype(int),
            }
        )
        reg = LinearRegression()
        reg.fit(features, df["y"])
        self._model = {"type": "fallback", "model": reg}

    def load(self) -> bool:
        """저장된 모델 로드."""
        if not self.model_path.exists():
            return False
        self._model = joblib.load(self.model_path)
        return True

    def predict_next_hour(self) -> list[dict]:
        """향후 60분, 5분 간격 예측."""
        if self._model is None and not self.load():
            df = self.generate_synthetic_data()
            self.train(
                [
                    {"recorded_at": row["ds"].to_pydatetime(), "value": row["y"]}
                    for _, row in df.iterrows()
                ]
            )

        if self._model is None:
            return self._fallback_predictions()

        if self._model.get("type") == "prophet":
            return self._predict_prophet(self._model["model"])
        return self._predict_sklearn(self._model["model"])

    def _predict_prophet(self, model: Any) -> list[dict]:
        future = model.make_future_dataframe(periods=12, freq="5min")
        forecast = model.predict(future)
        tail = forecast.tail(12)
        return self._format_predictions(
            tail["ds"].tolist(),
            tail["yhat"].tolist(),
            tail["yhat_lower"].tolist(),
            tail["yhat_upper"].tolist(),
        )

    def _predict_sklearn(self, model: LinearRegression) -> list[dict]:
        now = datetime.now(timezone.utc)
        times, preds = [], []
        for i in range(1, 13):
            ts = now + timedelta(minutes=5 * i)
            feat = pd.DataFrame(
                {
                    "hour": [ts.hour],
                    "minute": [ts.minute],
                    "weekday": [ts.weekday()],
                    "is_weekend": [1 if ts.weekday() >= 5 else 0],
                }
            )
            pred = float(model.predict(feat)[0])
            times.append(ts)
            preds.append(pred)
        return self._format_predictions(times, preds, preds, preds)

    def _format_predictions(
        self, times: list, predicted: list, lower: list, upper: list
    ) -> list[dict]:
        results = []
        for t, p, lo, hi in zip(times, predicted, lower, upper):
            ts = t.to_pydatetime() if hasattr(t, "to_pydatetime") else t
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            results.append(
                {
                    "time": ts,
                    "predicted": round(float(p), 2),
                    "lower": round(float(lo), 2),
                    "upper": round(float(hi), 2),
                    "will_exceed": float(p) > self.threshold,
                }
            )
        return results

    def generate_synthetic_data(self) -> pd.DataFrame:
        """현실적인 아파트 전력 패턴 합성 데이터."""
        np.random.seed(42)
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=14)
        timestamps = pd.date_range(start=start, end=now, freq="5min")

        values = []
        for ts in timestamps:
            hour = ts.hour
            is_weekend = ts.weekday() >= 5
            base = 8.0 if is_weekend else 10.0
            if 18 <= hour <= 21 and not is_weekend:
                base += 6.0 + np.sin((hour - 18) * np.pi / 3) * 3
            elif 7 <= hour <= 9:
                base += 3.0
            elif 12 <= hour <= 13:
                base += 2.0
            values.append(max(3.0, base + np.random.normal(0, 0.8)))

        return pd.DataFrame({"ds": timestamps, "y": values})

    def _to_prophet_df(self, readings: list[dict]) -> pd.DataFrame:
        rows = []
        for r in readings:
            ts = r.get("recorded_at") or r.get("time")
            val = r.get("value") or r.get("y")
            if ts is not None and val is not None:
                rows.append({"ds": pd.Timestamp(ts), "y": float(val)})
        return pd.DataFrame(rows)

    def _fallback_predictions(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        return [
            {
                "time": now + timedelta(minutes=5 * i),
                "predicted": 10.0,
                "lower": 8.0,
                "upper": 12.0,
                "will_exceed": False,
            }
            for i in range(1, 13)
        ]

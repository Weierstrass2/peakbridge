"""Prophet 예측기 단위 테스트."""

import numpy as np
import pytest

from app.ml.forecaster import PowerForecaster

try:
    from prophet import Prophet  # noqa: F401

    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False


@pytest.fixture
def forecaster(tmp_path) -> PowerForecaster:
    return PowerForecaster("test-building", model_dir=str(tmp_path))


@pytest.mark.skipif(not PROPHET_AVAILABLE, reason="prophet not installed")
class TestPowerForecaster:
    """합성 데이터 학습 및 MAE 검증."""

    def test_generate_synthetic_data(self, forecaster: PowerForecaster) -> None:
        df = forecaster.generate_synthetic_data()
        assert len(df) > 100
        assert "ds" in df.columns
        assert "y" in df.columns
        assert df["y"].min() >= 3.0

    def test_train_and_predict(self, forecaster: PowerForecaster) -> None:
        df = forecaster.generate_synthetic_data()
        readings = [
            {"recorded_at": row["ds"].to_pydatetime(), "value": row["y"]}
            for _, row in df.iterrows()
        ]
        forecaster.train(readings)
        predictions = forecaster.predict_next_hour()
        assert len(predictions) == 12
        assert all("predicted" in p for p in predictions)
        assert all("will_exceed" in p for p in predictions)

    def test_mae_below_threshold(self, forecaster: PowerForecaster) -> None:
        """MAE < 2.0A 검증 (sklearn 폴백 모델 holdout)."""
        import pandas as pd

        df = forecaster.generate_synthetic_data()
        split = int(len(df) * 0.8)
        train_data = df.iloc[:split]
        test_data = df.iloc[split : split + 200]

        forecaster._train_fallback(train_data)
        model = forecaster._model["model"]

        features = pd.DataFrame(
            {
                "hour": test_data["ds"].dt.hour,
                "minute": test_data["ds"].dt.minute,
                "weekday": test_data["ds"].dt.weekday,
                "is_weekend": (test_data["ds"].dt.weekday >= 5).astype(int),
            }
        )
        predicted = model.predict(features)
        actuals = test_data["y"].values
        mae = float(np.mean(np.abs(actuals - predicted)))
        assert mae < 2.0, f"MAE {mae:.2f}A exceeds 2.0A threshold"

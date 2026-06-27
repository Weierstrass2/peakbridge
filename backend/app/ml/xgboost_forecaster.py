"""
XGBoost 기반 전력 수요 예측 모델
KPX 한국전력거래소 실제 데이터 기반
"""

from __future__ import annotations

import joblib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.core.config import settings

try:
    import xgboost as xgb
except ImportError:
    xgb = None

# 공휴일 목록
HOLIDAYS = {
    "2023-01-01", "2023-01-21", "2023-01-22", "2023-01-23",
    "2023-03-01", "2023-05-05", "2023-05-15",
    "2023-06-06", "2023-08-15", "2023-09-28", "2023-09-29", "2023-09-30",
    "2023-10-03", "2023-10-09", "2023-12-25",
    "2024-01-01", "2024-02-09", "2024-02-10", "2024-02-11",
    "2024-03-01", "2024-05-05", "2024-05-15",
    "2024-06-06", "2024-08-15", "2024-09-16", "2024-09-17", "2024-09-18",
    "2024-10-03", "2024-10-09", "2024-12-25",
    "2025-01-01", "2025-01-30", "2025-01-31",
    "2025-03-01", "2025-05-05", "2025-05-15",
    "2025-06-06", "2025-08-15", "2025-09-20",
    "2025-10-03", "2025-10-09", "2025-12-25"
}


def is_holiday(dt: datetime) -> bool:
    return dt.strftime("%Y-%m-%d") in HOLIDAYS


class XGBoostForecaster:
    """XGBoost 기반 전력 수요 예측기"""

    FEATURE_LIST = [
        "hour", "minute", "weekday", "is_weekend", "is_holiday",
        "season", "hour_sin", "hour_cos", "month", "is_peak_hour",
        "lag_1h", "lag_24h", "rolling_mean_3h"
    ]

    def __init__(self, building_id: str):
        self.building_id = building_id
        self.model = None
        self.model_path = Path(f"/tmp/models/xgb_{building_id}.joblib")
        self.threshold = settings.PEAK_THRESHOLD_A
        self.trained_at = None
        self.mae = None
        self.rmse = None
        self.feature_importance = {}

        # 모델 디렉토리 생성
        self.model_path.parent.mkdir(parents=True, exist_ok=True)

    def _create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """특성 생성"""
        df = df.copy()
        df = df.sort_values("ds").reset_index(drop=True)

        df["hour"] = df["ds"].dt.hour
        df["minute"] = df["ds"].dt.minute
        df["weekday"] = df["ds"].dt.weekday
        df["month"] = df["ds"].dt.month

        # 계절
        def get_season(month):
            if 6 <= month <= 8:
                return 1
            elif 11 <= month or month <= 2:
                return 2
            else:
                return 0

        df["season"] = df["month"].apply(get_season)

        # 주말 여부
        df["is_weekend"] = (df["weekday"] >= 5).astype(int)

        # 공휴일 여부
        df["is_holiday"] = df["ds"].apply(is_holiday).astype(int)

        # 최대부하 시간대
        def is_peak_hour(hour):
            return 1 if (11 <= hour <= 13 or 17 <= hour <= 21) else 0

        df["is_peak_hour"] = df["hour"].apply(is_peak_hour)

        # 시간 주기성
        df["hour_sin"] = np.sin(df["hour"] * 2 * np.pi / 24)
        df["hour_cos"] = np.cos(df["hour"] * 2 * np.pi / 24)

        # Lag 특성
        df["lag_1h"] = df["y"].shift(1)
        df["lag_24h"] = df["y"].shift(24)

        # 롤링 평균
        df["rolling_mean_3h"] = df["y"].rolling(window=3).mean()

        # NaN 처리
        df = df.fillna(method="bfill").fillna(method="ffill")

        return df

    def train(self, df: pd.DataFrame) -> dict:
        """XGBoost 모델 학습"""
        if xgb is None:
            raise ImportError("XGBoost가 설치되지 않았습니다.")

        # 특성 생성
        df = self._create_features(df)

        # 학습/테스트 분할 (마지막 7일 테스트)
        train_size = int(len(df) * 0.9)
        train_df = df.iloc[:train_size]
        test_df = df.iloc[train_size:]

        X_train = train_df[self.FEATURE_LIST]
        y_train = train_df["y"]
        X_test = test_df[self.FEATURE_LIST]
        y_test = test_df["y"]

        # XGBoost 모델
        self.model = xgb.XGBRegressor(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1
        )

        self.model.fit(X_train, y_train)

        # 예측
        y_pred = self.model.predict(X_test)

        # 성능 지표
        self.mae = float(np.mean(np.abs(y_test - y_pred)))
        self.rmse = float(np.sqrt(np.mean((y_test - y_pred) ** 2)))

        # 특성 중요도
        feature_importance = self.model.get_booster().get_score(importance_type="weight")
        self.feature_importance = dict(sorted(feature_importance.items(), key=lambda x: x[1], reverse=True))

        self.trained_at = datetime.now(timezone.utc)

        # 모델 저장
        joblib.dump({
            "model": self.model,
            "mae": self.mae,
            "rmse": self.rmse,
            "trained_at": self.trained_at,
            "feature_importance": self.feature_importance
        }, self.model_path)

        return {
            "mae": self.mae,
            "rmse": self.rmse,
            "feature_importance": self.feature_importance
        }

    def load(self) -> bool:
        """저장된 모델 로드"""
        try:
            if not self.model_path.exists():
                return False

            data = joblib.load(self.model_path)
            self.model = data["model"]
            self.mae = data["mae"]
            self.rmse = data["rmse"]
            self.trained_at = data["trained_at"]
            self.feature_importance = data["feature_importance"]
            return True
        except Exception:
            return False

    def predict_next_hour(self, current_df: pd.DataFrame = None) -> List[Dict]:
        """향후 60분, 5분 간격 예측"""
        if self.model is None and not self.load():
            return []

        now = datetime.now(timezone.utc)
        predictions = []

        # 현재 데이터가 없으면 기본값으로 처리
        if current_df is None:
            # 최근 값 가져오기 위한 더미 데이터 생성
            current_df = pd.DataFrame([{
                "ds": now - timedelta(hours=24),
                "y": 10.0
            }])

        # 특성 생성
        df = self._create_features(current_df)

        # 최근 데이터 가져오기
        last_row = df.iloc[-1].copy()
        last_value = last_row["y"]

        for i in range(1, 13):
            pred_time = now + timedelta(minutes=5 * i)

            # 예측용 특성 생성
            pred_row = last_row.copy()
            pred_row["ds"] = pred_time
            pred_row["hour"] = pred_time.hour
            pred_row["minute"] = pred_time.minute
            pred_row["weekday"] = pred_time.weekday()
            pred_row["month"] = pred_time.month

            # 계절
            def get_season(month):
                if 6 <= month <= 8:
                    return 1
                elif 11 <= month or month <= 2:
                    return 2
                else:
                    return 0

            pred_row["season"] = get_season(pred_row["month"])
            pred_row["is_weekend"] = 1 if pred_row["weekday"] >= 5 else 0
            pred_row["is_holiday"] = 1 if is_holiday(pred_time) else 0

            def is_peak_hour(hour):
                return 1 if (11 <= hour <= 13 or 17 <= hour <= 21) else 0

            pred_row["is_peak_hour"] = is_peak_hour(pred_row["hour"])

            # 시간 주기성
            pred_row["hour_sin"] = np.sin(pred_row["hour"] * 2 * np.pi / 24)
            pred_row["hour_cos"] = np.cos(pred_row["hour"] * 2 * np.pi / 24)

            # Lag 특성
            pred_row["lag_1h"] = last_value
            pred_row["lag_24h"] = last_value

            # 롤링 평균
            pred_row["rolling_mean_3h"] = last_value

            # DataFrame으로 변환
            X_pred = pd.DataFrame([pred_row])[self.FEATURE_LIST]

            # 예측
            pred_value = float(self.model.predict(X_pred)[0])
            last_value = pred_value

            # Confidence interval (간단히 ±20%로)
            lower = pred_value * 0.8
            upper = pred_value * 1.2

            predictions.append({
                "time": pred_time,
                "predicted": round(pred_value, 2),
                "lower": round(lower, 2),
                "upper": round(upper, 2),
                "will_exceed": pred_value > self.threshold
            })

        return predictions

    def get_model_info(self) -> Dict:
        """모델 정보 반환"""
        if self.model is None and not self.load():
            return {
                "model_type": "XGBoost",
                "training_data": "KPX 한국전력거래소 실제 수요 데이터",
                "features": self.FEATURE_LIST,
                "mae": None,
                "trained_at": None
            }

        return {
            "model_type": "XGBoost",
            "training_data": "KPX 한국전력거래소 실제 수요 데이터",
            "features": self.FEATURE_LIST,
            "mae": self.mae,
            "rmse": self.rmse,
            "trained_at": self.trained_at.isoformat() if self.trained_at else None,
            "feature_importance": self.feature_importance
        }

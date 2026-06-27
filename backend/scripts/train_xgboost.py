#!/usr/bin/env python3
"""
XGBoost 모델 학습 스크립트
KPX 전력 수요 데이터 기반
"""

import pandas as pd
from pathlib import Path

# 프로젝트 루트 추가
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ml.xgboost_forecaster import XGBoostForecaster


def train_xgboost_model():
    data_dir = Path("data")
    processed_path = data_dir / "kpx_processed.csv"

    # 데이터 로드
    if not processed_path.exists():
        print("전처리된 데이터가 없습니다. download_kpx_data.py를 먼저 실행하세요.")
        return None

    print("KPX 전처리 데이터 로딩 중...")
    df = pd.read_csv(processed_path, parse_dates=["ds"])
    print(f"데이터 로드 완료: {len(df)}개 행")

    # 모델 학습
    print("\nXGBoost 모델 학습 중...")
    forecaster = XGBoostForecaster("building-A")
    result = forecaster.train(df)

    # 결과 출력
    print("\n=== 학습 결과 ===")
    print(f"MAE: {result['mae']:.2f}A")
    print(f"RMSE: {result['rmse']:.2f}A")
    print("\n특성 중요도:")
    for feat, imp in list(result["feature_importance"].items())[:10]:
        print(f"  {feat}: {imp:.2f}")

    print("\n학습 완료: MAE={:.2f}A, RMSE={:.2f}A".format(result['mae'], result['rmse']))
    print("KPX 실제 데이터 기반 XGBoost 모델 저장 완료")

    # 예측 테스트
    print("\n=== 예측 테스트 ===")
    predictions = forecaster.predict_next_hour()
    print(f"향후 60분 예측: {len(predictions)}개")
    for pred in predictions[:3]:
        print(f"  {pred['time'].strftime('%H:%M')}: {pred['predicted']:.2f}A")

    return result


if __name__ == "__main__":
    train_xgboost_model()

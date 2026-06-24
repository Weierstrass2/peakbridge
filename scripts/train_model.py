#!/usr/bin/env python3
"""
실제 DB 데이터로 Prophet 모델 재학습하는 스크립트
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.core.constants import SensorType
from app.ml.forecaster import PowerForecaster
from app.repositories.sensor_repository import SensorRepository
from app.models.sensor_reading import SensorReading
from app.models.device import Device

settings = get_settings()


async def main():
    print("=== Prophet 모델 학습 시작 ===")
    building_id = "building-A"
    
    # 데이터베이스 엔진 생성
    engine = create_async_engine(settings.DB_URL, echo=False)
    
    async with AsyncSession(engine) as session:
        sensor_repo = SensorRepository(session)
        
        # 1. DB에서 esp32-grid-01의 14일치 데이터 조회
        print("1. DB에서 데이터 조회 중...")
        readings = await sensor_repo.get_readings_for_training(
            building_id, SensorType.GRID_CURRENT.value
        )
        print(f"   조회된 데이터 수: {len(readings)}개")
        
        if len(readings) < 10:
            print("   오류: 데이터가 너무 적습니다!")
            return
        
        # 데이터를 리스트로 변환
        data = [
            {"recorded_at": r.recorded_at, "value": r.value} 
            for r in readings
        ]
        
        # 2. Prophet 모델 학습
        print("2. Prophet 모델 학습 중...")
        forecaster = PowerForecaster(building_id)
        forecaster.train(data)
        print("   학습 완료!")
        
        # 3. 모델 저장
        print("3. 모델 저장 중...")
        model_path = Path(settings.ML_MODEL_DIR) / f"forecaster_{building_id}.joblib"
        print(f"   저장 경로: {model_path}")
        # forecaster.train()에서 이미 저장하므로 여기서는 확인만
        if model_path.exists():
            print("   저장 완료!")
        
        # 4. 예측 테스트: 향후 60분 예측값 출력
        print("\n4. 향후 60분 예측 테스트:")
        predictions = forecaster.predict_next_hour()
        for p in predictions:
            time_str = p["time"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(p["time"], datetime) else p["time"]
            exceed_str = "⚠️ 피크 초과 예상" if p["will_exceed"] else ""
            print(f"   {time_str} | 예측: {p['predicted']:.2f}A (범위: {p['lower']:.2f}~{p['upper']:.2f}A) {exceed_str}")
        
        # 5. MAE 계산 (최근 200개 데이터로 테스트)
        print("\n5. MAE (평균 절대 오차) 계산:")
        if len(data) >= 200:
            test_data = data[-200:]  # 최근 200개
            train_data = data[:-200]  # 나머지로 학습
            
            # 임시 모델로 학습
            temp_forecaster = PowerForecaster("temp", model_dir=str(Path(settings.ML_MODEL_DIR) / "temp"))
            temp_forecaster.train(train_data)
            
            # 실제값과 예측값 비교
            actuals = [d["value"] for d in test_data]
            
            # Prophet 모델의 predict 메서드로 과거 예측
            if temp_forecaster._model and temp_forecaster._model.get("type") == "prophet":
                prophet_model = temp_forecaster._model["model"]
                # 테스트 데이터의 타임스탬프로 DataFrame 생성
                import pandas as pd
                test_df = pd.DataFrame({
                    "ds": [pd.Timestamp(d["recorded_at"]) for d in test_data]
                })
                forecast = prophet_model.predict(test_df)
                predicted = forecast["yhat"].values
            else:
                # sklearn 폴백 모델
                predicted = []
                model = temp_forecaster._model["model"]
                for d in test_data:
                    dt = d["recorded_at"]
                    import pandas as pd
                    feat = pd.DataFrame({
                        "hour": [dt.hour],
                        "minute": [dt.minute],
                        "weekday": [dt.weekday()],
                        "is_weekend": [1 if dt.weekday() >= 5 else 0],
                    })
                    pred = float(model.predict(feat)[0])
                    predicted.append(pred)
            
            mae = float(np.mean(np.abs(np.array(actuals) - np.array(predicted))))
            print(f"   MAE: {mae:.2f}A")
        else:
            print("   데이터가 적어 MAE 계산 스킵")
    
    print("\n=== 모델 학습 완료 ===")


if __name__ == "__main__":
    asyncio.run(main())

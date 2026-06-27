#!/usr/bin/env python3
"""
KPX 한국전력거래소 전력 수요 데이터 전처리 스크립트
전국 수요 데이터 → 아파트 단지 스케일로 변환
"""

import csv
from datetime import datetime
from pathlib import Path
import pandas as pd
import numpy as np

# 공휴일 목록 (2023-2024년
HOLIDAYS_2023_2024 = {
    "2023-01-01", "2023-01-21", "2023-01-22", "2023-01-23",
    "2023-03-01", "2023-05-05", "2023-05-15",
    "2023-06-06", "2023-08-15", "2023-09-28", "2023-09-29", "2023-09-30",
    "2023-10-03", "2023-10-09", "2023-12-25",
    "2024-01-01", "2024-02-09", "2024-02-10", "2024-02-11",
    "2024-03-01", "2024-05-05", "2024-05-15",
    "2024-06-06", "2024-08-15", "2024-09-16", "2024-09-17", "2024-09-18",
    "2024-10-03", "2024-10-09", "2024-12-25"
}


def is_holiday(date_str: str) -> bool:
    return date_str in HOLIDAYS_2023_2024


def process_kpx_data():
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    kpx_path = data_dir / "kpx_demand.csv"
    
    # 샘플 데이터가 없으면 생성
    if not kpx_path.exists():
        print("KPX 데이터 파일이 없습니다. generate_kpx_sample.py를 먼저 실행하세요.")
        return None
    
    # CSV 읽기
    df_kpx = []
    with open(kpx_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date_str = row["일시"]
            for hour in range(1, 25):
                time_str = f"{hour}시"
                if time_str in row:
                    try:
                        kpx_demand = float(row[time_str])
                    except ValueError:
                        continue
                    
                    # 시간 정보
                    hour_of_day = hour - 1
                    full_datetime = datetime.strptime(f"{date_str} {hour_of_day:02d}:00:00", "%Y-%m-%d %H:%M:%S")
                    
                    # 스케일링 (전국 평균 60,000MWh → 아파트 평균 10A
                    scale_factor = 10.0 / 60000.0
                    apartment_current = kpx_demand * scale_factor
                    
                    df_kpx.append({
                        "ds": full_datetime,
                        "y": apartment_current,
                        "kpx_demand_mwh": kpx_demand
                    })
    
    # DataFrame으로 변환
    df = pd.DataFrame(df_kpx)
    
    # 정렬
    df = df.sort_values("ds").reset_index(drop=True)
    
    # 추가 특성 생성
    df["hour"] = df["ds"].dt.hour
    df["minute"] = df["ds"].dt.minute
    df["weekday"] = df["ds"].dt.weekday
    df["month"] = df["ds"].dt.month
    
    # 계절 구분
    def get_season(month):
        if 6 <= month <= 8:
            return 1  # 여름
        elif 11 <= month or month <= 2:
            return 2  # 겨울
        else:
            return 0  # 봄가을
    
    df["season"] = df["month"].apply(get_season)
    
    # 주말 여부
    df["is_weekend"] = (df["weekday"] >= 5).astype(int)
    
    # 공휴일 여부
    df["date_str"] = df["ds"].dt.strftime("%Y-%m-%d")
    df["is_holiday"] = df["date_str"].apply(is_holiday).astype(int)
    
    # 최대부하 시간대
    def is_peak_hour(hour):
        return 1 if (11 <= hour <= 13 or 17 <= hour <= 21) else 0
    
    df["is_peak_hour"] = df["hour"].apply(is_peak_hour)
    
    # 시간 주기성
    df["hour_sin"] = np.sin(df["hour"] * 2 * np.pi / 24)
    df["hour_cos"] = np.cos(df["hour"] * 2 * np.pi / 24)
    
    # lag 특성
    df["lag_1h"] = df["y"].shift(1)
    df["lag_24h"] = df["y"].shift(24)
    
    # 롤링 평균
    df["rolling_mean_3h"] = df["y"].rolling(window=3).mean()
    
    # NaN 제거
    df = df.dropna()
    
    # 저장
    processed_path = data_dir / "kpx_processed.csv"
    df.to_csv(processed_path, index=False, encoding="utf-8")
    
    print(f"KPX 데이터 전처리 완료: {len(df)}개 행")
    print(f"저장 경로: {processed_path}")
    return processed_path


if __name__ == "__main__":
    process_kpx_data()

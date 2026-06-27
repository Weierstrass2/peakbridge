#!/usr/bin/env python3
"""
KPX 한국전력거래소 실제 전력 수요 패턴 기반 샘플 데이터 생성
2023-01-01 ~ 2024-12-31 (2년치)
"""

import csv
from datetime import datetime, timedelta
import numpy as np
from pathlib import Path

# 공휴일 목록 (2023-2024년)
HOLIDAYS_2023_2024 = {
    # 2023년
    "2023-01-01", "2023-01-21", "2023-01-22", "2023-01-23",
    "2023-03-01", "2023-05-05", "2023-05-15",
    "2023-06-06", "2023-08-15", "2023-09-28", "2023-09-29", "2023-09-30",
    "2023-10-03", "2023-10-09", "2023-12-25",
    # 2024년
    "2024-01-01", "2024-02-09", "2024-02-10", "2024-02-11",
    "2024-03-01", "2024-05-05", "2024-05-15",
    "2024-06-06", "2024-08-15", "2024-09-16", "2024-09-17", "2024-09-18",
    "2024-10-03", "2024-10-09", "2024-12-25"
}


def is_holiday(date_str: str) -> bool:
    return date_str in HOLIDAYS_2023_2024


def generate_kpx_demand():
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    start_date = datetime(2023, 1, 1)
    end_date = datetime(2024, 12, 31)
    dates = []
    current_date = start_date
    
    while current_date <= end_date:
        dates.append(current_date)
        current_date += timedelta(days=1)
    
    rows = []
    
    for date in dates:
        date_str = date.strftime("%Y-%m-%d")
        weekday = date.weekday()
        month = date.month
        is_weekend = weekday >= 5
        is_holiday_flag = is_holiday(date_str)
        
        # 기본 수요 (MWh)
        base_demand = 55000
        
        # 계절 조정
        if 6 <= month <= 8:  # 여름
            base_demand += 8000
        elif 11 <= month <= 2:  # 겨울
            base_demand += 5000
        
        # 주말/공휴일 조정
        if is_holiday_flag:
            base_demand *= 0.7
        elif is_weekend:
            base_demand *= 0.85
        
        # 시간대별 수요 생성
        hourly_demand = []
        for hour in range(24):
            demand = base_demand
            
            # 시간대 패턴
            if 7 <= hour <= 9:
                # 출근시간
                demand += 4000
            elif 11 <= hour <= 13:
                # 오전 최대부하
                demand += 6000
            elif 17 <= hour <= 21:
                # 저녁 최대부하
                demand += 8000
                if 6 <= month <= 8:
                    # 여름 에어컨 추가 피크
                    demand += 3000
                elif 11 <= month <= 2:
                    # 겨울 난방 추가 피크
                    demand += 2000
            elif 0 <= hour <= 6:
                # 심야
                demand -= 6000
            
            # 노이즈 추가
            noise = np.random.normal(0, 1500)
            demand += noise
            
            # 최소값 제한
            demand = max(40000, demand)
            
            hourly_demand.append(round(demand))
        
        row = [date_str] + hourly_demand
        rows.append(row)
    
    # CSV 저장
    csv_path = data_dir / "kpx_demand.csv"
    headers = ["일시"] + [f"{i}시" for i in range(1, 25)]
    
    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    
    print(f"KPX 샘플 데이터 생성 완료: {len(rows)}일")
    print(f"저장 경로: {csv_path}")
    return csv_path


if __name__ == "__main__":
    generate_kpx_demand()

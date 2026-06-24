#!/usr/bin/env python3
"""
2주치 현실적인 센서 데이터를 생성해서 PostgreSQL DB에 삽입하는 스크립트
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# 프로젝트 루트 경로를 sys.path에 추가
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.db.base import Base
from app.models.device import Device
from app.models.sensor_reading import SensorReading

settings = get_settings()

# 디바이스 설정
DEVICES = [
    {"device_id": "esp32-grid-01", "name": "Grid Meter 01", "device_type": "grid_meter", "building_id": "building-A"},
    {"device_id": "esp32-ess-01", "name": "ESS 01", "device_type": "ess", "building_id": "building-A"},
    {"device_id": "esp32-charger-01", "name": "Charger 01", "device_type": "charger", "building_id": "building-A"},
    {"device_id": "esp32-charger-02", "name": "Charger 02", "device_type": "charger", "building_id": "building-A"},
    {"device_id": "esp32-charger-03", "name": "Charger 03", "device_type": "charger", "building_id": "building-A"},
    {"device_id": "esp32-charger-04", "name": "Charger 04", "device_type": "charger", "building_id": "building-A"},
]

# 기간 설정
END_DATE = datetime.now(timezone.utc)
START_DATE = END_DATE - timedelta(days=14)
INTERVAL = timedelta(minutes=5)


def generate_grid_current(dt: datetime) -> float:
    """현실적인 grid_current 값 생성"""
    hour = dt.hour
    is_weekend = dt.weekday() >= 5  # 5=토, 6=일
    
    base = 0.0
    if is_weekend:
        # 주말 패턴
        if 13 <= hour < 16:
            base = 15.0  # 주말 피크
        else:
            base = 8.0
        base *= 0.8  # 주말은 전체적으로 20% 낮음
    else:
        # 평일 패턴
        if 0 <= hour < 6:
            base = 4.0  # 심야
        elif 6 <= hour < 9:
            base = 10.0  # 출근
        elif 9 <= hour < 17:
            base = 7.5  # 낮
        elif 17 <= hour < 21:
            base = 18.5  # 퇴근 피크
        else:
            base = 10.0  # 저녁
    
    # 노이즈 추가 (±1~2)
    noise = np.random.normal(0, 1.5)
    return max(0.0, round(base + noise, 2))


def generate_ess_soc(dt: datetime, prev_soc: float) -> float:
    """현실적인 ess_soc 값 생성 (이전 값 기반)"""
    hour = dt.hour
    
    if 1 <= hour < 5:
        # 심야 충전: 60→90%
        target_soc = min(90.0, prev_soc + 0.5)
    elif 17 <= hour < 21:
        # 피크 방전: 90→25%
        target_soc = max(25.0, prev_soc - 1.3)
    else:
        # 나머지 시간: 유지 + 약간의 노이즈
        target_soc = prev_soc + np.random.normal(0, 0.3)
    
    return round(np.clip(target_soc, 0.0, 100.0), 2)


def generate_charger_current(dt: datetime) -> float:
    """현실적인 charger_current 값 생성"""
    hour = dt.hour
    is_peak = (17 <= hour < 21) or (13 <= hour < 16 and dt.weekday() >= 5)
    
    if is_peak:
        base = np.random.uniform(5.0, 8.0)
    else:
        base = np.random.uniform(0.0, 2.0)
    
    # 30% 확률로 0 (충전 안 함)
    if np.random.random() < 0.3:
        base = 0.0
    
    return round(base, 2)


async def seed_devices(session: AsyncSession) -> int:
    """디바이스 6개 등록 (없으면 INSERT, 있으면 SKIP)"""
    count = 0
    for device_data in DEVICES:
        # 기존 디바이스 확인
        result = await session.execute(
            select(Device).where(Device.device_id == device_data["device_id"])
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            device = Device(
                id=uuid.uuid4(),
                device_id=device_data["device_id"],
                name=device_data["name"],
                device_type=device_data["device_type"],
                building_id=device_data["building_id"],
                status="online",
                registered_at=START_DATE,
            )
            session.add(device)
            count += 1
    
    await session.commit()
    return count


async def seed_sensor_data(session: AsyncSession) -> int:
    """센서 데이터 생성 및 삽입"""
    total_count = 0
    current_time = START_DATE
    
    # ESS SOC 초기값
    ess_prev_soc = 60.0
    
    # 총 타임스탬프 수 계산
    total_timestamps = int((END_DATE - START_DATE) / INTERVAL)
    print(f"총 타임스탬프 수: {total_timestamps}")
    
    readings = []
    
    while current_time < END_DATE:
        # 1. 그리드 전류
        grid_value = generate_grid_current(current_time)
        readings.append(
            SensorReading(
                id=uuid.uuid4(),
                device_id="esp32-grid-01",
                sensor_type="grid_current",
                value=grid_value,
                unit="A",
                recorded_at=current_time,
            )
        )
        
        # 2. ESS SOC
        ess_soc = generate_ess_soc(current_time, ess_prev_soc)
        readings.append(
            SensorReading(
                id=uuid.uuid4(),
                device_id="esp32-ess-01",
                sensor_type="ess_soc",
                value=ess_soc,
                unit="%",
                recorded_at=current_time,
            )
        )
        ess_prev_soc = ess_soc
        
        # 3. 충전기 4개
        for i in range(1, 5):
            charger_value = generate_charger_current(current_time)
            readings.append(
                SensorReading(
                    id=uuid.uuid4(),
                    device_id=f"esp32-charger-0{i}",
                    sensor_type="charger_current",
                    value=charger_value,
                    unit="A",
                    recorded_at=current_time,
                )
            )
        
        current_time += INTERVAL
        total_count += 6  # 1 grid + 1 ess + 4 chargers
        
        # 진행 상황 출력 (1000개마다)
        if total_count % 1000 == 0:
            print(f"데이터 삽입 중... {total_count}/{total_timestamps * 6}")
    
    # 벌크 삽입
    session.add_all(readings)
    await session.commit()
    
    return total_count


async def main():
    """메인 함수"""
    print("=== PeakBridge 센서 데이터 시딩 시작 ===")
    
    # 데이터베이스 엔진 생성
    engine = create_async_engine(settings.DB_URL, echo=False)
    
    async with AsyncSession(engine) as session:
        # 1. 디바이스 등록
        print("디바이스 등록 중...")
        device_count = await seed_devices(session)
        print(f"디바이스 등록 완료: {device_count}개 신규, 총 {len(DEVICES)}개")
        
        # 2. 센서 데이터 삽입
        print("센서 데이터 생성 및 삽입 중...")
        data_count = await seed_sensor_data(session)
        print(f"완료! 총 {data_count}개 데이터 삽입")
    
    print("=== 시딩 완료 ===")


if __name__ == "__main__":
    asyncio.run(main())

"""센서 측정값 Repository — 시계열 조회/저장."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sensor_reading import SensorReading


class SensorRepository:
    """sensor_readings 테이블 접근."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, reading: SensorReading) -> SensorReading:
        """단일 측정값 저장."""
        self.session.add(reading)
        await self.session.flush()
        return reading

    async def bulk_create(self, readings: list[SensorReading]) -> list[SensorReading]:
        """배치 측정값 저장."""
        self.session.add_all(readings)
        await self.session.flush()
        return readings

    async def get_latest(
        self, device_id: str, sensor_type: str
    ) -> SensorReading | None:
        """디바이스·센서 타입별 최신값."""
        result = await self.session.execute(
            select(SensorReading)
            .where(
                SensorReading.device_id == device_id,
                SensorReading.sensor_type == sensor_type,
            )
            .order_by(SensorReading.recorded_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_by_building(
        self, building_id: str, sensor_type: str, device_type: str
    ) -> SensorReading | None:
        """건물 내 특정 디바이스 타입의 최신 센서값."""
        from app.models.device import Device

        result = await self.session.execute(
            select(SensorReading)
            .join(Device, Device.device_id == SensorReading.device_id)
            .where(
                Device.building_id == building_id,
                Device.device_type == device_type,
                SensorReading.sensor_type == sensor_type,
            )
            .order_by(SensorReading.recorded_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_history(
        self,
        device_id: str,
        from_time: datetime,
        to_time: datetime,
        sensor_type: str | None = None,
    ) -> list[SensorReading]:
        """기간별 원본 측정값 조회."""
        query = select(SensorReading).where(
            SensorReading.device_id == device_id,
            SensorReading.recorded_at >= from_time,
            SensorReading.recorded_at <= to_time,
        )
        if sensor_type:
            query = query.where(SensorReading.sensor_type == sensor_type)
        query = query.order_by(SensorReading.recorded_at.asc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_aggregated_history(
        self,
        device_id: str,
        from_time: datetime,
        to_time: datetime,
        interval: str,
        sensor_type: str | None = None,
    ) -> list[dict]:
        """시간 버킷별 평균값 집계 (1min|5min|1hour)."""
        bucket_map = {"1min": "minute", "5min": "minute", "1hour": "hour"}
        trunc_unit = bucket_map.get(interval, "minute")

        bucket_expr = func.date_trunc(trunc_unit, SensorReading.recorded_at)
        if interval == "5min":
            bucket_expr = func.date_trunc("hour", SensorReading.recorded_at) + (
                func.floor(
                    func.extract("minute", SensorReading.recorded_at) / 5
                )
                * func.make_interval(0, 0, 0, 0, 0, 5)
            )

        query = (
            select(
                bucket_expr.label("bucket"),
                func.avg(SensorReading.value).label("avg_value"),
                SensorReading.unit,
            )
            .where(
                SensorReading.device_id == device_id,
                SensorReading.recorded_at >= from_time,
                SensorReading.recorded_at <= to_time,
            )
            .group_by(bucket_expr, SensorReading.unit)
            .order_by(bucket_expr.asc())
        )
        if sensor_type:
            query = query.where(SensorReading.sensor_type == sensor_type)

        result = await self.session.execute(query)
        rows = result.all()
        return [
            {
                "time": row.bucket,
                "avg_value": float(row.avg_value),
                "unit": row.unit,
            }
            for row in rows
        ]

    async def get_readings_for_training(
        self, building_id: str, sensor_type: str, limit: int = 10000
    ) -> list[SensorReading]:
        """Prophet 학습용 과거 grid_current 데이터."""
        from app.models.device import Device

        result = await self.session.execute(
            select(SensorReading)
            .join(Device, Device.device_id == SensorReading.device_id)
            .where(
                Device.building_id == building_id,
                SensorReading.sensor_type == sensor_type,
            )
            .order_by(SensorReading.recorded_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

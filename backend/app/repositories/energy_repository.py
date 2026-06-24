"""에너지 절감 집계 Repository."""

from datetime import date
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.energy_saving import EnergySaving


class EnergyRepository:
    """energy_savings 테이블 접근."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def increment_savings(
        self,
        building_id: str,
        saved_kwh: float,
        saved_won: float,
        co2_reduced_kg: float,
        peak_inc: int = 0,
    ) -> EnergySaving:
        """당일 절감량 누적 증가."""
        today = date.today()
        existing = await self.get_by_date(building_id, today)
        if existing:
            existing.saved_kwh += saved_kwh
            existing.saved_won += saved_won
            existing.co2_reduced_kg += co2_reduced_kg
            existing.peak_count += peak_inc
            await self.session.flush()
            return existing

        record = EnergySaving(
            building_id=building_id,
            date=today,
            saved_kwh=saved_kwh,
            saved_won=saved_won,
            co2_reduced_kg=co2_reduced_kg,
            peak_count=peak_inc,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_by_date(
        self, building_id: str, target_date: date
    ) -> EnergySaving | None:
        """특정 일자 절감 데이터."""
        result = await self.session.execute(
            select(EnergySaving).where(
                EnergySaving.building_id == building_id,
                EnergySaving.date == target_date,
            )
        )
        return result.scalar_one_or_none()

    async def get_period_summary(
        self,
        building_id: str,
        period: Literal["day", "week", "month", "year"],
    ) -> dict:
        """기간별 절감량 합계."""
        today = date.today()
        if period == "day":
            start = today
        elif period == "week":
            start = today.replace(day=max(1, today.day - 7))
        elif period == "month":
            start = today.replace(day=1)
        else:
            start = today.replace(month=1, day=1)

        result = await self.session.execute(
            select(
                func.coalesce(func.sum(EnergySaving.saved_kwh), 0),
                func.coalesce(func.sum(EnergySaving.saved_won), 0),
                func.coalesce(func.sum(EnergySaving.co2_reduced_kg), 0),
                func.coalesce(func.sum(EnergySaving.peak_count), 0),
            ).where(
                EnergySaving.building_id == building_id,
                EnergySaving.date >= start,
                EnergySaving.date <= today,
            )
        )
        row = result.one()
        return {
            "saved_kwh": float(row[0]),
            "saved_won": float(row[1]),
            "co2_reduced_kg": float(row[2]),
            "peak_count": int(row[3]),
        }

    async def get_month_total(self, building_id: str) -> float:
        """이번 달 절감액 합계."""
        summary = await self.get_period_summary(building_id, "month")
        return summary["saved_won"]

    async def export_csv_rows(
        self, building_id: str, start: date, end: date
    ) -> list[EnergySaving]:
        """CSV 내보내기용 기간 데이터."""
        result = await self.session.execute(
            select(EnergySaving)
            .where(
                EnergySaving.building_id == building_id,
                EnergySaving.date >= start,
                EnergySaving.date <= end,
            )
            .order_by(EnergySaving.date.asc())
        )
        return list(result.scalars().all())

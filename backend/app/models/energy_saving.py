"""일별 에너지 절감 집계 ORM 모델."""

import uuid
from datetime import date

from sqlalchemy import Date, Float, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EnergySaving(Base):
    """건물별 일별 절감량·비용·CO2 집계."""

    __tablename__ = "energy_savings"
    __table_args__ = (
        UniqueConstraint("building_id", "date", name="uq_energy_saving_building_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    building_id: Mapped[str] = mapped_column(String(64), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    saved_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    saved_won: Mapped[float] = mapped_column(Float, default=0.0)
    co2_reduced_kg: Mapped[float] = mapped_column(Float, default=0.0)
    peak_count: Mapped[int] = mapped_column(Integer, default=0)

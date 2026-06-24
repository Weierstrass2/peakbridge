"""센서 시계열 측정값 ORM 모델."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SensorReading(Base):
    """디바이스별 센서 측정값 — TimescaleDB hypertable 후보."""

    __tablename__ = "sensor_readings"
    __table_args__ = (
        Index("ix_sensor_readings_device_recorded", "device_id", "recorded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.device_id"), index=True
    )
    sensor_type: Mapped[str] = mapped_column(String(32))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    device: Mapped["Device"] = relationship("Device", back_populates="readings")

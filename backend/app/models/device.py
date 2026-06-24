"""IoT 디바이스(그리드 미터, ESS, 충전기) ORM 모델."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    """UTC 현재 시각."""
    return datetime.now(timezone.utc)


class Device(Base):
    """건물에 등록된 센서/제어 디바이스."""

    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    device_type: Mapped[str] = mapped_column(String(32))
    building_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="offline")
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    readings: Mapped[list["SensorReading"]] = relationship(
        "SensorReading", back_populates="device", lazy="selectin"
    )

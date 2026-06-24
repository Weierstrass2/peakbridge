"""피크 감지 및 피크쉐이빙 알림 ORM 모델."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Alert(Base):
    """건물별 피크/제어 관련 알림."""

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    building_id: Mapped[str] = mapped_column(String(64), index=True)
    alert_type: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16))
    grid_current: Mapped[float] = mapped_column(Float)
    ess_soc: Mapped[float] = mapped_column(Float)
    reduction_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

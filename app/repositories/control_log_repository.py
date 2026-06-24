"""제어 로그 Repository."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.control_log import ControlLog


class ControlLogRepository:
    """control_logs 테이블 접근."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, log: ControlLog) -> ControlLog:
        """제어 로그 기록."""
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_last_action(
        self, building_id: str, within_seconds: int = 30
    ) -> ControlLog | None:
        """최근 제어 명령 — 멱등성 검사용."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
        result = await self.session.execute(
            select(ControlLog)
            .where(
                ControlLog.building_id == building_id,
                ControlLog.created_at >= cutoff,
            )
            .order_by(ControlLog.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_recent(
        self, building_id: str, limit: int = 20
    ) -> list[ControlLog]:
        """최근 제어 이력."""
        result = await self.session.execute(
            select(ControlLog)
            .where(ControlLog.building_id == building_id)
            .order_by(ControlLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

"""알림 Repository."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert


class AlertRepository:
    """alerts 테이블 접근."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, alert: Alert) -> Alert:
        """알림 생성."""
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def get_by_id(self, alert_id: uuid.UUID) -> Alert | None:
        """ID로 알림 조회."""
        result = await self.session.execute(
            select(Alert).where(Alert.id == alert_id)
        )
        return result.scalar_one_or_none()

    async def list_recent(self, building_id: str, limit: int = 50) -> list[Alert]:
        """건물별 최근 알림."""
        result = await self.session.execute(
            select(Alert)
            .where(Alert.building_id == building_id)
            .order_by(Alert.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_unresolved(
        self, building_id: str, within_minutes: int | None = None
    ) -> list[Alert]:
        """미해결 알림 (peak_detected / peak_shaving_activated).

        within_minutes: 지정하면 그 시간 안에 생성된 것만 센다.
            피크 해제 처리는 인메모리 상태(_peak_state)에 의존하는데, 서버가
            재시작되면 그 상태가 초기화되어 '해제' 분기를 못 타고 DB 알림이
            영구히 미해결로 남는다. 그 잔재가 대시보드를 계속 '피크 중'으로
            보이게 하므로, 현재 상태 판정에는 신선도 창을 건다.
        """
        conds = [
            Alert.building_id == building_id,
            Alert.resolved_at.is_(None),
            Alert.alert_type.in_(["peak_detected", "peak_shaving_activated"]),
        ]
        if within_minutes is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=within_minutes)
            conds.append(Alert.created_at >= cutoff)
        result = await self.session.execute(select(Alert).where(*conds))
        return list(result.scalars().all())

    async def has_active_peak(
        self, building_id: str, within_minutes: int | None = 15
    ) -> bool:
        """현재 피크 활성 여부 (기본: 최근 15분 내 미해결 피크 알림)."""
        unresolved = await self.list_unresolved(building_id, within_minutes)
        return len(unresolved) > 0

    async def resolve(self, alert_id: uuid.UUID) -> Alert | None:
        """알림 해결 처리."""
        alert = await self.get_by_id(alert_id)
        if not alert:
            return None
        alert.resolved_at = datetime.now(timezone.utc)
        await self.session.flush()
        return alert

    async def resolve_all_peak(self, building_id: str) -> int:
        """건물의 모든 미해결 피크 알림 일괄 해결."""
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            update(Alert)
            .where(
                Alert.building_id == building_id,
                Alert.resolved_at.is_(None),
            )
            .values(resolved_at=now)
        )
        return result.rowcount or 0

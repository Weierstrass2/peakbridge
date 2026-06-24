"""디바이스 CRUD Repository."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device


class DeviceRepository:
    """devices 테이블 접근."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_device_id(self, device_id: str) -> Device | None:
        """device_id로 디바이스 조회."""
        result = await self.session.execute(
            select(Device).where(Device.device_id == device_id)
        )
        return result.scalar_one_or_none()

    async def create(self, device: Device) -> Device:
        """새 디바이스 등록."""
        self.session.add(device)
        await self.session.flush()
        return device

    async def update_last_seen(self, device_id: str) -> None:
        """마지막 통신 시각 갱신."""
        now = datetime.now(timezone.utc)
        await self.session.execute(
            update(Device)
            .where(Device.device_id == device_id)
            .values(last_seen_at=now, status="online")
        )

    async def list_by_building(
        self, building_id: str, device_type: str | None = None
    ) -> list[Device]:
        """건물별 디바이스 목록."""
        query = select(Device).where(Device.building_id == building_id)
        if device_type:
            query = query.where(Device.device_type == device_type)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_or_create(
        self,
        device_id: str,
        name: str,
        device_type: str,
        building_id: str,
    ) -> Device:
        """디바이스 조회, 없으면 자동 등록."""
        device = await self.get_by_device_id(device_id)
        if device:
            return device
        device = Device(
            id=uuid.uuid4(),
            device_id=device_id,
            name=name,
            device_type=device_type,
            building_id=building_id,
        )
        return await self.create(device)

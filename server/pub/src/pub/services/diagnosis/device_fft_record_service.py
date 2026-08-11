"""Device FFT Record Service."""

from typing import List
from uuid import UUID

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from pub.models.sensor import DeviceFftRecord


class DeviceFftRecordService:
    @staticmethod
    async def list_for_device(
        session: AsyncSession,
        tenant_id: UUID,
        device_inst_id: UUID,
        limit: int = 50,
    ) -> List[DeviceFftRecord]:
        """Fetch FFT records for a specific device."""
        stmt = (
            select(DeviceFftRecord)
            .where(
                DeviceFftRecord.tenant_id == tenant_id,
                DeviceFftRecord.device_inst_id == device_inst_id,
            )
            .order_by(desc(DeviceFftRecord.created_at))
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        tenant_id: UUID,
        record_id: UUID,
    ) -> DeviceFftRecord | None:
        """Fetch a specific FFT record by ID."""
        stmt = select(DeviceFftRecord).where(
            DeviceFftRecord.id == record_id,
            DeviceFftRecord.tenant_id == tenant_id,
        )
        return (await session.execute(stmt)).scalar_one_or_none()

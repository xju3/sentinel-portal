"""
Device service - business logic for device operations
"""

from uuid import UUID
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_

from pub.models.device import (
    IsoStandard,
    DeviceCategory,
    DeviceSpec,
    DeviceInst,
    Process,
    ProcessItem,
    ProcessDevice,
    ProcessDeviceItem,
)
from pub.models.sensor import SensorMonitoring
from pub.models.customer import HealthCheckFreq
from pub.utils.sorting import apply_sorting

class DeviceCategoryService:
    @staticmethod
    async def get_all(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        keyword: Optional[str] = None,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[DeviceCategory]:
        stmt = select(DeviceCategory).where(DeviceCategory.tenant_id == tenant_id)
        if keyword:
            like_kw = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    DeviceCategory.name.ilike(like_kw),
                    DeviceCategory.description.ilike(like_kw),
                )
            )
        stmt = apply_sorting(stmt, DeviceCategory, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def count_all(
        session: AsyncSession,
        tenant_id: UUID,
        keyword: Optional[str] = None,
    ) -> int:
        stmt = select(func.count(DeviceCategory.id)).where(DeviceCategory.tenant_id == tenant_id)
        if keyword:
            like_kw = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    DeviceCategory.name.ilike(like_kw),
                    DeviceCategory.description.ilike(like_kw),
                )
            )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def has_children(session: AsyncSession, tenant_id: UUID, obj_id: UUID) -> bool:
        stmt = (
            select(DeviceCategory.id)
            .where(
                DeviceCategory.parent_id == obj_id,
                DeviceCategory.tenant_id == tenant_id,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        tenant_id: UUID,
        obj_id: UUID,
    ) -> Optional[DeviceCategory]:
        stmt = select(DeviceCategory).where(
            DeviceCategory.id == obj_id,
            DeviceCategory.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_health_check_freq_map(
        session: AsyncSession,
        tenant_id: UUID,
        freq_ids: List[UUID],
    ) -> dict[UUID, HealthCheckFreq]:
        if not freq_ids:
            return {}
        stmt = select(HealthCheckFreq).where(
            HealthCheckFreq.tenant_id == tenant_id,
            HealthCheckFreq.id.in_(freq_ids),
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return {row.id: row for row in rows}

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> DeviceCategory:
        db_obj = DeviceCategory(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(session: AsyncSession, db_obj: DeviceCategory, data: dict) -> DeviceCategory:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: DeviceCategory) -> None:
        await session.delete(db_obj)
        await session.commit()

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

class DeviceInstService:
    @staticmethod
    async def get_all(
        session: AsyncSession,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[DeviceInst]:
        stmt = select(DeviceInst)
        stmt = apply_sorting(stmt, DeviceInst, sort_by, sort_order or "ascend")
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_by_id(session: AsyncSession, obj_id: UUID) -> Optional[DeviceInst]:
        stmt = select(DeviceInst).where(DeviceInst.id == obj_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def is_tenant_device_inst(
        session: AsyncSession,
        tenant_id: UUID,
        device_inst_id: UUID,
    ) -> bool:
        stmt = (
            select(DeviceInst.id)
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(
                DeviceInst.id == device_inst_id,
                DeviceCategory.tenant_id == tenant_id,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_tenant_device_insts_paged(
        session: AsyncSession,
        tenant_id: UUID,
        current: int,
        page_size: int,
        keyword: Optional[str] = None,
    ) -> tuple:
        """Get paged DeviceInsts scoped to tenant, with total count."""
        from pub.models.customer import Location as LocationModel

        base_join = (
            select(DeviceInst)
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(DeviceCategory.tenant_id == tenant_id)
        )
        if keyword:
            like = f"%{keyword}%"
            base_join = base_join.where(
                or_(DeviceInst.name.ilike(like), DeviceInst.code.ilike(like))
            )

        count_stmt = select(func.count()).select_from(base_join.subquery())
        count_result = await session.execute(count_stmt)
        total = count_result.scalar() or 0

        skip = (current - 1) * page_size
        fetch_stmt = base_join.offset(skip).limit(page_size)
        result = await session.execute(fetch_stmt)
        items = result.scalars().all()

        return items, total

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> DeviceInst:
        db_obj = DeviceInst(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(session: AsyncSession, db_obj: DeviceInst, data: dict) -> DeviceInst:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: DeviceInst) -> None:
        await session.delete(db_obj)
        await session.commit()


def generate_standard_service(model_class):
    """Factory class to generate basic CRUD services to avoid excessive boilerplate"""

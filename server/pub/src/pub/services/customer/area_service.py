"""
Customer service - business logic for customer operations
"""

from uuid import UUID
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_

from pub.models.customer import (
    Region,
    Tenant,
    TenantSensor,
    Supplier,
    Contact,
    Account,
    Area,
    Location,
    HealthCheckFreq,
    IsoStandard,
)
from pub.exceptions.domain_exception import DomainException
from pub.utils.sorting import apply_sorting

from pub.models.sensor import SensorMonitoring, Sensor
from pub.models.device import DeviceCategory, DeviceSpec, DeviceInst

class AreaService:
    @staticmethod
    async def get_areas(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[Area]:
        stmt = (
            select(Area)
            .where(Area.tenant_id == tenant_id)
        )
        stmt = apply_sorting(stmt, Area, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_area(
        session: AsyncSession,
        tenant_id: UUID,
        area_id: UUID,
    ) -> Optional[Area]:
        stmt = select(Area).where(
            Area.id == area_id,
            Area.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_area(session: AsyncSession, data: dict) -> Area:
        db_area = Area(**data)
        session.add(db_area)
        await session.commit()
        await session.refresh(db_area)
        return db_area

    @staticmethod
    async def update_area(
        session: AsyncSession,
        db_area: Area,
        data: dict,
    ) -> Area:
        for key, value in data.items():
            setattr(db_area, key, value)
        await session.commit()
        await session.refresh(db_area)
        return db_area

    @staticmethod
    async def delete_area(session: AsyncSession, db_area: Area) -> None:
        await session.delete(db_area)
        await session.commit()

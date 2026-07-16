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

class IsoStandardService:
    @staticmethod
    async def get_iso_standards(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[IsoStandard]:
        stmt = select(IsoStandard).where(IsoStandard.tenant_id == tenant_id)
        stmt = apply_sorting(stmt, IsoStandard, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def count_iso_standards(
        session: AsyncSession,
        tenant_id: UUID,
    ) -> int:
        stmt = select(func.count(IsoStandard.id)).where(IsoStandard.tenant_id == tenant_id)
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def get_iso_standard(
        session: AsyncSession,
        tenant_id: UUID,
        iso_id: UUID,
    ) -> Optional[IsoStandard]:
        stmt = select(IsoStandard).where(
            IsoStandard.id == iso_id,
            IsoStandard.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_iso_standard(session: AsyncSession, data: dict) -> IsoStandard:
        db_obj = IsoStandard(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update_iso_standard(
        session: AsyncSession,
        db_obj: IsoStandard,
        data: dict,
    ) -> IsoStandard:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete_iso_standard(session: AsyncSession, db_obj: IsoStandard) -> None:
        await session.delete(db_obj)
        await session.commit()

    @staticmethod
    async def get_all(
        session: AsyncSession,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[IsoStandard]:
        stmt = select(IsoStandard)
        stmt = apply_sorting(stmt, IsoStandard, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()


    @staticmethod
    async def get_by_id(session: AsyncSession, obj_id: UUID) -> Optional[IsoStandard]:
        stmt = select(IsoStandard).where(IsoStandard.id == obj_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


    @staticmethod
    async def create(session: AsyncSession, data: dict) -> IsoStandard:
        db_obj = IsoStandard(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj


    @staticmethod
    async def update(session: AsyncSession, db_obj: IsoStandard, data: dict) -> IsoStandard:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj


    @staticmethod
    async def delete(session: AsyncSession, db_obj: IsoStandard) -> None:
        await session.delete(db_obj)
        await session.commit()

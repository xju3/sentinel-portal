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

class TenantService:
    @staticmethod
    async def get_tenants(
        session: AsyncSession,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[Tenant]:
        stmt = select(Tenant)
        stmt = apply_sorting(stmt, Tenant, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_tenant(session: AsyncSession, tenant_id: UUID) -> Optional[Tenant]:
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_tenant(session: AsyncSession, data: dict) -> Tenant:
        db_tenant = Tenant(**data)
        session.add(db_tenant)
        await session.commit()
        await session.refresh(db_tenant)
        return db_tenant

    @staticmethod
    async def update_tenant(session: AsyncSession, db_tenant: Tenant, data: dict) -> Tenant:
        for key, value in data.items():
            setattr(db_tenant, key, value)
        await session.commit()
        await session.refresh(db_tenant)
        return db_tenant

    @staticmethod
    async def delete_tenant(session: AsyncSession, db_tenant: Tenant) -> None:
        await session.delete(db_tenant)
        await session.commit()

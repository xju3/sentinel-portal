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
        active: bool | None = None,
        code: Optional[str] = None,
        name: Optional[str] = None,
        mqtt_server: Optional[str] = None,
        api_server: Optional[str] = None,
        status: Optional[int] = None,
        email_status: Optional[int] = None,
        industry: Optional[int] = None,
        email: Optional[str] = None,
        region_id: Optional[str] = None,
    ) -> tuple[List[Tenant], int]:
        stmt = select(Tenant)
        if active is not None:
            if isinstance(active, str):
                active = active.lower() == "true"
            stmt = stmt.where(Tenant.active == active)
        if code:
            stmt = stmt.where(Tenant.code.ilike(f"%{code.strip()}%"))
        if name:
            stmt = stmt.where(Tenant.name.ilike(f"%{name.strip()}%"))
        if mqtt_server:
            stmt = stmt.where(Tenant.mqtt_server.ilike(f"%{mqtt_server.strip()}%"))
        if api_server:
            stmt = stmt.where(Tenant.api_server.ilike(f"%{api_server.strip()}%"))
        if status is not None:
            stmt = stmt.where(Tenant.status == status)
        if email_status is not None:
            stmt = stmt.where(Tenant.email_status == email_status)
        if industry is not None:
            stmt = stmt.where(Tenant.industry == industry)
        if email:
            stmt = stmt.where(Tenant.email.ilike(f"%{email.strip()}%"))
        if region_id:
            stmt = stmt.where(Tenant.region_id == region_id.strip())

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        stmt = apply_sorting(stmt, Tenant, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all(), total

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

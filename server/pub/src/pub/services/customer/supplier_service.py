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

class SupplierService:
    @staticmethod
    async def get_suppliers(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        keyword: Optional[str] = None,
        sort_by: str | None = None,
        sort_order: str = "ascend",
        name: Optional[str] = None,
        brand: Optional[str] = None,
        contact_info: Optional[str] = None,
        active: Optional[bool] = None,
    ) -> tuple[List[Supplier], int]:
        stmt = select(Supplier).where(Supplier.tenant_id == tenant_id)
        if keyword:
            like_kw = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    Supplier.name.ilike(like_kw),
                    Supplier.brand.ilike(like_kw),
                    Supplier.contact_info.ilike(like_kw),
                )
            )
        if name:
            stmt = stmt.where(Supplier.name.ilike(f"%{name.strip()}%"))
        if brand:
            stmt = stmt.where(Supplier.brand.ilike(f"%{brand.strip()}%"))
        if contact_info:
            stmt = stmt.where(Supplier.contact_info.ilike(f"%{contact_info.strip()}%"))
        if active is not None:
            if isinstance(active, str):
                active = active.lower() == 'true'
            stmt = stmt.where(Supplier.active == active)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        stmt = apply_sorting(stmt, Supplier, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all(), total

    @staticmethod
    async def count_suppliers(
        session: AsyncSession,
        tenant_id: UUID,
        keyword: Optional[str] = None,
    ) -> int:
        stmt = select(func.count(Supplier.id)).where(Supplier.tenant_id == tenant_id)
        if keyword:
            like_kw = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    Supplier.name.ilike(like_kw),
                    Supplier.brand.ilike(like_kw),
                    Supplier.contact_info.ilike(like_kw),
                )
            )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def get_supplier(
        session: AsyncSession,
        tenant_id: UUID,
        supplier_id: UUID,
    ) -> Optional[Supplier]:
        stmt = select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_supplier(session: AsyncSession, data: dict) -> Supplier:
        db_supplier = Supplier(**data)
        session.add(db_supplier)
        await session.commit()
        await session.refresh(db_supplier)
        return db_supplier

    @staticmethod
    async def update_supplier(session: AsyncSession, db_supplier: Supplier, data: dict) -> Supplier:
        for key, value in data.items():
            setattr(db_supplier, key, value)
        await session.commit()
        await session.refresh(db_supplier)
        return db_supplier

    @staticmethod
    async def delete_supplier(session: AsyncSession, db_supplier: Supplier) -> None:
        await session.delete(db_supplier)
        await session.commit()

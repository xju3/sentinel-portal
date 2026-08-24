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

class LocationService:
    @staticmethod
    async def get_locations(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
        keyword: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[int] = None,
        is_bearing_point: Optional[bool] = None,
        bearing_only: bool = False,
        active_only: bool = False,
    ) -> tuple[List[Location], int]:
        stmt = select(Location).where(Location.tenant_id == tenant_id)
        if keyword:
            like = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(Location.name.ilike(like), Location.description.ilike(like))
            )
        if name:
            stmt = stmt.where(Location.name.ilike(f"%{name.strip()}%"))
        if description:
            stmt = stmt.where(Location.description.ilike(f"%{description.strip()}%"))
        if status is not None:
            stmt = stmt.where(Location.status == status)
        if is_bearing_point is not None:
            stmt = stmt.where(Location.is_bearing_point.is_(is_bearing_point))
        if bearing_only:
            stmt = stmt.where(Location.is_bearing_point.is_(True))
        if active_only:
            stmt = stmt.where(Location.status == 1)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        stmt = apply_sorting(stmt, Location, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all(), total

    @staticmethod
    async def get_location(
        session: AsyncSession,
        tenant_id: UUID,
        location_id: UUID,
    ) -> Optional[Location]:
        stmt = select(Location).where(
            Location.id == location_id,
            Location.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def is_tenant_location(
        session: AsyncSession,
        tenant_id: UUID,
        location_id: UUID,
        active_only: bool = False,
    ) -> bool:
        """Check if a location belongs to the given tenant."""
        stmt = select(Location.id).where(
            Location.id == location_id,
            Location.tenant_id == tenant_id,
        )
        if active_only:
            stmt = stmt.where(Location.status == 1)
        stmt = stmt.limit(1)
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_paged_locations(
        session: AsyncSession,
        tenant_id: UUID,
        current: int,
        page_size: int,
        keyword: Optional[str] = None,
        bearing_only: bool = False,
        active_only: bool = False,
    ) -> tuple:
        """Get paged locations with total count. Returns (items, total)."""
        base_stmt = select(Location).where(Location.tenant_id == tenant_id)
        if bearing_only:
            base_stmt = base_stmt.where(Location.is_bearing_point.is_(True))
        if active_only:
            base_stmt = base_stmt.where(Location.status == 1)
        if keyword:
            like = f"%{keyword}%"
            base_stmt = base_stmt.where(Location.name.ilike(like))

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        count_result = await session.execute(count_stmt)
        total = count_result.scalar() or 0

        skip = (current - 1) * page_size
        fetch_stmt = base_stmt.offset(skip).limit(page_size)
        result = await session.execute(fetch_stmt)
        items = result.scalars().all()

        return items, total

    @staticmethod
    async def create_location(session: AsyncSession, data: dict) -> Location:
        db_obj = Location(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update_location(
        session: AsyncSession,
        db_obj: Location,
        data: dict,
    ) -> Location:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def disable_location(session: AsyncSession, db_obj: Location) -> Location:
        """Disable a location without breaking historical foreign-key references."""
        db_obj.status = 0
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

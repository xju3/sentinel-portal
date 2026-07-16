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

class TenantSensorService:
    @staticmethod
    async def get_tenant_sensors(
        session: AsyncSession,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[TenantSensor]:
        stmt = select(TenantSensor)
        stmt = apply_sorting(stmt, TenantSensor, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_tenant_sensor(session: AsyncSession, ts_id: UUID) -> Optional[TenantSensor]:
        stmt = select(TenantSensor).where(TenantSensor.id == ts_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_tenant_sensor(session: AsyncSession, data: dict) -> TenantSensor:
        db_ts = TenantSensor(**data)
        session.add(db_ts)
        await session.commit()
        await session.refresh(db_ts)
        return db_ts

    @staticmethod
    async def update_tenant_sensor(session: AsyncSession, db_ts: TenantSensor, data: dict) -> TenantSensor:
        for key, value in data.items():
            setattr(db_ts, key, value)
        await session.commit()
        await session.refresh(db_ts)
        return db_ts

    @staticmethod
    async def delete_tenant_sensor(session: AsyncSession, db_ts: TenantSensor) -> None:
        await session.delete(db_ts)
        await session.commit()

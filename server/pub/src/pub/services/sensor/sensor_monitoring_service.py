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

class SensorMonitoringService:
    """Service for SensorMonitoring with tenant-scoped queries."""

    @staticmethod
    async def get_all(
        session: AsyncSession,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ):
        from pub.models.device import DeviceInst
        stmt = (
            select(SensorMonitoring)
            .join(DeviceInst, SensorMonitoring.device_inst_id == DeviceInst.id)
        )
        stmt = apply_sorting(stmt, SensorMonitoring, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_by_code(session: AsyncSession, code: str):
        stmt = select(SensorMonitoring).where(SensorMonitoring.code == code and SensorMonitoring.status == 1)
        result = await session.execute(stmt)
        return result.scalar_one_or_none() 

    @staticmethod
    async def get_by_id(session: AsyncSession, obj_id: UUID):
        stmt = select(SensorMonitoring).where(SensorMonitoring.id == obj_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_by_tenant(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ):
        """Get SensorMonitoring records scoped to a tenant."""
        from pub.models.device import DeviceInst, DeviceSpec, DeviceCategory

        stmt = (
            select(SensorMonitoring)
            .join(DeviceInst, SensorMonitoring.device_inst_id == DeviceInst.id)
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(DeviceCategory.tenant_id == tenant_id)
        )
        stmt = apply_sorting(stmt, SensorMonitoring, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_by_id_and_tenant(
        session: AsyncSession,
        obj_id: UUID,
        tenant_id: UUID,
    ):
        """Get a SensorMonitoring record by id, scoped to a tenant."""
        from pub.models.device import DeviceInst, DeviceSpec, DeviceCategory

        stmt = (
            select(SensorMonitoring)
            .join(DeviceInst, SensorMonitoring.device_inst_id == DeviceInst.id)
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(
                SensorMonitoring.id == obj_id,
                DeviceCategory.tenant_id == tenant_id,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, data: dict):
        db_obj = SensorMonitoring(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(session: AsyncSession, db_obj, data: dict):
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj) -> None:
        await session.delete(db_obj)
        await session.commit()


from pub.services.common.crud_factory import get_crud_service

ProcessService = get_crud_service(Process)
ProcessItemService = get_crud_service(ProcessItem)
ProcessDeviceService = get_crud_service(ProcessDevice)
ProcessDeviceItemService = get_crud_service(ProcessDeviceItem)

# Backward-compatible aliases for legacy router names.
DeviceComboSpecService = ProcessService
DeviceComboSpecItemService = ProcessItemService
DeviceComboInstService = ProcessDeviceService
DeviceComboInstItemService = ProcessDeviceItemService
DeviceInstTagService = SensorMonitoringService

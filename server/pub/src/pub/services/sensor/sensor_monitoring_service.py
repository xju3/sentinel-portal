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
        old_sensor_id = db_obj.sensor_id
        old_device_inst_id = db_obj.device_inst_id
        old_status = db_obj.status

        for key, value in data.items():
            setattr(db_obj, key, value)
            
        from pub.services.sensor.sensor_task_service import create_manual_sensor_task, SYSTEM_ACTION_UPDATE_BINDING
        
        # 只要关键的绑定信息（传感器、设备、状态）发生了改变，就对所有涉及到的传感器下发任务
        if old_sensor_id != db_obj.sensor_id or old_device_inst_id != db_obj.device_inst_id or old_status != db_obj.status:
            sensors_to_notify = set()
            if old_sensor_id:
                sensors_to_notify.add(old_sensor_id)
            if db_obj.sensor_id:
                sensors_to_notify.add(db_obj.sensor_id)
                
            for sid in sensors_to_notify:
                await create_manual_sensor_task(
                    session=session,
                    sensor_id=sid,
                    name="update_binding",
                    action=SYSTEM_ACTION_UPDATE_BINDING,
                    val=0,
                    remark="Monitoring relation updated",
                )

        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj) -> None:
        if db_obj.sensor_id:
            from pub.services.sensor.sensor_task_service import create_manual_sensor_task, SYSTEM_ACTION_UPDATE_BINDING
            await create_manual_sensor_task(
                session=session,
                sensor_id=db_obj.sensor_id,
                name="update_binding",
                action=SYSTEM_ACTION_UPDATE_BINDING,
                val=0,
                remark="Monitoring deleted",
            )
        await session.delete(db_obj)
        await session.commit()


from pub.services.common.crud_factory import get_crud_service

ProcessService = get_crud_service(Process)
ProcessItemService = get_crud_service(ProcessItem)
ProcessDeviceItemService = get_crud_service(ProcessDeviceItem)

_ProcessDeviceCRUD = get_crud_service(ProcessDevice)

class ProcessDeviceService(_ProcessDeviceCRUD):
    @staticmethod
    async def get_all(
        session: AsyncSession,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[ProcessDevice]:
        from sqlalchemy.orm import selectinload
        stmt = select(ProcessDevice)
        stmt = apply_sorting(stmt, ProcessDevice, sort_by, sort_order)
        stmt = stmt.options(selectinload(ProcessDevice.employees))
        stmt = stmt.options(selectinload(ProcessDevice.process))
        stmt = stmt.options(selectinload(ProcessDevice.area))
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_by_id(session: AsyncSession, obj_id: UUID) -> Optional[ProcessDevice]:
        from sqlalchemy.orm import selectinload
        stmt = select(ProcessDevice).where(ProcessDevice.id == obj_id)
        stmt = stmt.options(selectinload(ProcessDevice.employees))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    @staticmethod
    async def update_members(
        session: AsyncSession,
        tenant_id: UUID,
        db_obj: ProcessDevice,
        employee_ids: List[UUID],
    ) -> None:
        from pub.models.device import ProcessDeviceEmployee
        from sqlalchemy import delete
        from datetime import datetime

        # Delete existing associations
        await session.execute(
            delete(ProcessDeviceEmployee).where(
                ProcessDeviceEmployee.process_device_id == db_obj.id
            )
        )

        # Insert new associations explicitly
        for emp_id in employee_ids:
            new_mapping = ProcessDeviceEmployee(
                process_device_id=db_obj.id,
                employee_id=emp_id,
                trans_date=datetime.utcnow(),
                status=True,
            )
            session.add(new_mapping)

        await session.commit()
        await session.refresh(db_obj)

# Backward-compatible aliases for legacy router names.
DeviceComboSpecService = ProcessService
DeviceComboSpecItemService = ProcessItemService
DeviceComboInstService = ProcessDeviceService
DeviceComboInstItemService = ProcessDeviceItemService
DeviceInstTagService = SensorMonitoringService

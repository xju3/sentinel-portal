"""Tenant-scoped services for process templates and process devices."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pub.models.device import (
    DeviceInst,
    Process,
    ProcessDevice,
    ProcessDeviceItem,
    ProcessItem,
)
from pub.models.org import Employee
from pub.utils.sorting import apply_sorting


class ProcessService:
    @staticmethod
    async def get_all(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[Process]:
        stmt = select(Process).where(Process.tenant_id == tenant_id)
        stmt = apply_sorting(stmt, Process, sort_by, sort_order or "ascend")
        result = await session.execute(stmt.offset(skip).limit(limit))
        return result.scalars().all()

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        tenant_id: UUID,
        obj_id: UUID,
    ) -> Optional[Process]:
        stmt = select(Process).where(
            Process.id == obj_id,
            Process.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_code(
        session: AsyncSession,
        tenant_id: UUID,
        code: str,
        exclude_id: UUID | None = None,
    ) -> Optional[Process]:
        stmt = select(Process).where(
            Process.tenant_id == tenant_id,
            Process.code == code,
        )
        if exclude_id is not None:
            stmt = stmt.where(Process.id != exclude_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> Process:
        db_obj = Process(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(session: AsyncSession, db_obj: Process, data: dict) -> Process:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: Process) -> None:
        await session.delete(db_obj)
        await session.commit()


class ProcessItemService:
    @staticmethod
    async def get_all(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[ProcessItem]:
        stmt = (
            select(ProcessItem)
            .join(Process, ProcessItem.process_id == Process.id)
            .where(Process.tenant_id == tenant_id)
        )
        stmt = apply_sorting(stmt, ProcessItem, sort_by, sort_order or "ascend")
        result = await session.execute(stmt.offset(skip).limit(limit))
        return result.scalars().all()

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        tenant_id: UUID,
        obj_id: UUID,
    ) -> Optional[ProcessItem]:
        stmt = (
            select(ProcessItem)
            .join(Process, ProcessItem.process_id == Process.id)
            .where(
                ProcessItem.id == obj_id,
                Process.tenant_id == tenant_id,
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> ProcessItem:
        db_obj = ProcessItem(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(
        session: AsyncSession,
        db_obj: ProcessItem,
        data: dict,
    ) -> ProcessItem:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: ProcessItem) -> None:
        await session.delete(db_obj)
        await session.commit()


class ProcessDeviceService:
    @staticmethod
    async def get_all(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
        device_spec_id: UUID | None = None,
    ) -> List[ProcessDevice]:
        stmt = (
            select(ProcessDevice)
            .join(Process, ProcessDevice.process_id == Process.id)
            .where(Process.tenant_id == tenant_id)
            .options(
                selectinload(ProcessDevice.employees),
                selectinload(ProcessDevice.process),
                selectinload(ProcessDevice.area),
            )
        )
        if device_spec_id is not None:
            stmt = (
                stmt.join(
                    ProcessDeviceItem,
                    ProcessDeviceItem.process_device_id == ProcessDevice.id,
                )
                .join(
                    DeviceInst,
                    DeviceInst.id == ProcessDeviceItem.device_inst_id,
                )
                .where(DeviceInst.device_spec_id == device_spec_id)
                .distinct()
            )
        stmt = apply_sorting(stmt, ProcessDevice, sort_by, sort_order or "ascend")
        result = await session.execute(stmt.offset(skip).limit(limit))
        return result.scalars().all()

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        tenant_id: UUID,
        obj_id: UUID,
    ) -> Optional[ProcessDevice]:
        stmt = (
            select(ProcessDevice)
            .join(Process, ProcessDevice.process_id == Process.id)
            .where(
                ProcessDevice.id == obj_id,
                Process.tenant_id == tenant_id,
            )
            .options(
                selectinload(ProcessDevice.employees),
                selectinload(ProcessDevice.process),
                selectinload(ProcessDevice.area),
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> ProcessDevice:
        db_obj = ProcessDevice(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(
        session: AsyncSession,
        db_obj: ProcessDevice,
        data: dict,
    ) -> ProcessDevice:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: ProcessDevice) -> None:
        await session.delete(db_obj)
        await session.commit()

    @staticmethod
    async def update_members(
        session: AsyncSession,
        tenant_id: UUID,
        db_obj: ProcessDevice,
        employee_ids: List[UUID],
    ) -> None:
        if employee_ids:
            stmt = select(Employee).where(
                Employee.tenant_id == tenant_id,
                Employee.id.in_(employee_ids),
            )
            employees = (await session.execute(stmt)).scalars().all()
        else:
            employees = []
        db_obj.employees = list(employees)
        await session.commit()
        await session.refresh(db_obj)


class ProcessDeviceItemService:
    @staticmethod
    async def get_all(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[ProcessDeviceItem]:
        stmt = (
            select(ProcessDeviceItem)
            .join(
                ProcessDevice,
                ProcessDeviceItem.process_device_id == ProcessDevice.id,
            )
            .join(Process, ProcessDevice.process_id == Process.id)
            .where(Process.tenant_id == tenant_id)
        )
        stmt = apply_sorting(
            stmt,
            ProcessDeviceItem,
            sort_by,
            sort_order or "ascend",
        )
        result = await session.execute(stmt.offset(skip).limit(limit))
        return result.scalars().all()

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        tenant_id: UUID,
        obj_id: UUID,
    ) -> Optional[ProcessDeviceItem]:
        stmt = (
            select(ProcessDeviceItem)
            .join(
                ProcessDevice,
                ProcessDeviceItem.process_device_id == ProcessDevice.id,
            )
            .join(Process, ProcessDevice.process_id == Process.id)
            .where(
                ProcessDeviceItem.id == obj_id,
                Process.tenant_id == tenant_id,
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> ProcessDeviceItem:
        db_obj = ProcessDeviceItem(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(
        session: AsyncSession,
        db_obj: ProcessDeviceItem,
        data: dict,
    ) -> ProcessDeviceItem:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: ProcessDeviceItem) -> None:
        await session.delete(db_obj)
        await session.commit()

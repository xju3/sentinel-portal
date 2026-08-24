"""Tenant-scoped services for process templates and process devices."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, or_, select
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


def _apply_model_filters(stmt, model, **filters):
    for key, value in filters.items():
        if value is None or not hasattr(model, key):
            continue

        column = getattr(model, key)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
            stmt = stmt.where(column.ilike(f"%{value}%"))
        else:
            stmt = stmt.where(column == value)

    return stmt


async def _paginate(
    session: AsyncSession,
    stmt,
    model,
    skip: int,
    limit: int,
    sort_by: str | None,
    sort_order: str,
):
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = apply_sorting(stmt, model, sort_by, sort_order or "ascend")
    result = await session.execute(stmt.offset(skip).limit(limit))
    return result.scalars().all(), total


class ProcessService:
    @staticmethod
    async def get_all(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
        **kwargs,
    ) -> tuple[List[Process], int]:
        stmt = select(Process).where(Process.tenant_id == tenant_id)
        keyword = kwargs.pop("keyword", None)
        if keyword:
            like_keyword = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    Process.code.ilike(like_keyword),
                    Process.name.ilike(like_keyword),
                    Process.remark.ilike(like_keyword),
                )
            )
        stmt = _apply_model_filters(stmt, Process, **kwargs)
        return await _paginate(
            session,
            stmt,
            Process,
            skip,
            limit,
            sort_by,
            sort_order,
        )

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
        **kwargs,
    ) -> tuple[List[ProcessItem], int]:
        stmt = (
            select(ProcessItem)
            .join(Process, ProcessItem.process_id == Process.id)
            .where(Process.tenant_id == tenant_id)
            .options(selectinload(ProcessItem.device_spec))
        )
        stmt = _apply_model_filters(stmt, ProcessItem, **kwargs)
        return await _paginate(
            session,
            stmt,
            ProcessItem,
            skip,
            limit,
            sort_by,
            sort_order,
        )

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
        keyword: str | None = None,
        code: str | None = None,
        sn: str | None = None,
        process_id: UUID | None = None,
        area_id: UUID | None = None,
        status: int | None = None,
        device_spec_id: UUID | None = None,
    ) -> tuple[List[ProcessDevice], int]:
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
        if keyword:
            like_keyword = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    ProcessDevice.code.ilike(like_keyword),
                    ProcessDevice.sn.ilike(like_keyword),
                )
            )
        stmt = _apply_model_filters(
            stmt,
            ProcessDevice,
            code=code,
            sn=sn,
            process_id=process_id,
            area_id=area_id,
            status=status,
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
        return await _paginate(
            session,
            stmt,
            ProcessDevice,
            skip,
            limit,
            sort_by,
            sort_order,
        )

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
        **kwargs,
    ) -> tuple[List[ProcessDeviceItem], int]:
        stmt = (
            select(ProcessDeviceItem)
            .join(
                ProcessDevice,
                ProcessDeviceItem.process_device_id == ProcessDevice.id,
            )
            .join(Process, ProcessDevice.process_id == Process.id)
            .where(Process.tenant_id == tenant_id)
        )
        stmt = _apply_model_filters(
            stmt,
            ProcessDeviceItem,
            **kwargs,
        )
        return await _paginate(
            session,
            stmt,
            ProcessDeviceItem,
            skip,
            limit,
            sort_by,
            sort_order,
        )

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

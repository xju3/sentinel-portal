"""
Device service - business logic for device operations
"""

from uuid import UUID
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import exists, func, or_
from sqlalchemy.orm import selectinload

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

class DeviceSpecService:
    @staticmethod
    async def is_tenant_device_spec(
        session: AsyncSession,
        tenant_id: UUID,
        device_spec_id: UUID,
    ) -> bool:
        stmt = (
            select(DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(
                DeviceSpec.id == device_spec_id,
                DeviceCategory.tenant_id == tenant_id,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_all(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
        process_device_id: UUID | None = None,
        in_device_group: bool = False,
        name: str | None = None,
        model: str | None = None,
        brand: str | None = None,
        supplier_id: UUID | None = None,
        device_category_id: UUID | None = None,
        rpm: int | None = None,
        voltage: float | None = None,
    ) -> tuple[List[DeviceSpec], int]:
        stmt = (
            select(DeviceSpec)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(DeviceCategory.tenant_id == tenant_id)
        )
        if process_device_id is not None:
            stmt = (
                stmt.join(DeviceInst, DeviceInst.device_spec_id == DeviceSpec.id)
                .join(
                    ProcessDeviceItem,
                    ProcessDeviceItem.device_inst_id == DeviceInst.id,
                )
                .join(
                    ProcessDevice,
                    ProcessDevice.id == ProcessDeviceItem.process_device_id,
                )
                .join(Process, Process.id == ProcessDevice.process_id)
                .where(
                    ProcessDeviceItem.process_device_id == process_device_id,
                    Process.tenant_id == tenant_id,
                )
                .distinct()
            )

        if in_device_group:
            group_exists = (
                select(ProcessDeviceItem.id)
                .select_from(ProcessDeviceItem)
                .join(DeviceInst, ProcessDeviceItem.device_inst_id == DeviceInst.id)
                .join(ProcessDevice, ProcessDevice.id == ProcessDeviceItem.process_device_id)
                .join(Process, Process.id == ProcessDevice.process_id)
                .where(
                    DeviceInst.device_spec_id == DeviceSpec.id,
                    Process.tenant_id == tenant_id,
                )
            )
            stmt = stmt.where(exists(group_exists))

        if name:
            stmt = stmt.where(DeviceSpec.name.ilike(f"%{name.strip()}%"))
        if model:
            stmt = stmt.where(DeviceSpec.model.ilike(f"%{model.strip()}%"))
        if brand:
            stmt = stmt.where(DeviceSpec.brand.ilike(f"%{brand.strip()}%"))
        if supplier_id is not None:
            stmt = stmt.where(DeviceSpec.supplier_id == supplier_id)
        if device_category_id is not None:
            stmt = stmt.where(DeviceSpec.device_category_id == device_category_id)
        if rpm is not None:
            stmt = stmt.where(DeviceSpec.rpm == rpm)
        if voltage is not None:
            stmt = stmt.where(DeviceSpec.voltage == voltage)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        stmt = apply_sorting(stmt, DeviceSpec, sort_by, sort_order or "ascend")
        if in_device_group:
            # A stable tie-breaker prevents duplicates or gaps between pages.
            stmt = stmt.order_by(DeviceSpec.id.asc())
        stmt = stmt.options(
            selectinload(DeviceSpec.supplier),
            selectinload(DeviceSpec.device_category),
        ).offset(skip).limit(limit)
        result = await session.execute(stmt)
        items = result.scalars().all()
        await DeviceSpecService._attach_process_devices(
            session, tenant_id, items
        )
        return items, total

    @staticmethod
    async def _attach_process_devices(
        session: AsyncSession,
        tenant_id: UUID,
        specs: List[DeviceSpec],
    ) -> None:
        if not specs:
            return
        spec_ids = [spec.id for spec in specs]
        stmt = (
            select(
                DeviceInst.device_spec_id,
                ProcessDevice.id,
                ProcessDevice.code,
                ProcessDevice.sn,
            )
            .join(
                ProcessDeviceItem,
                ProcessDeviceItem.device_inst_id == DeviceInst.id,
            )
            .join(
                ProcessDevice,
                ProcessDevice.id == ProcessDeviceItem.process_device_id,
            )
            .join(Process, Process.id == ProcessDevice.process_id)
            .where(
                DeviceInst.device_spec_id.in_(spec_ids),
                Process.tenant_id == tenant_id,
            )
            .distinct()
        )
        rows = (await session.execute(stmt)).all()
        process_devices: dict[UUID, list[dict]] = {}
        for spec_id, item_id, code, sn in rows:
            process_devices.setdefault(spec_id, []).append(
                {"id": item_id, "code": code, "sn": sn}
            )
        for spec in specs:
            spec.process_devices = process_devices.get(spec.id, [])
            spec.process_device_count = len(spec.process_devices)

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        tenant_id: UUID,
        obj_id: UUID,
    ) -> Optional[DeviceSpec]:
        stmt = (
            select(DeviceSpec)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(
                DeviceSpec.id == obj_id,
                DeviceCategory.tenant_id == tenant_id,
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> DeviceSpec:
        db_obj = DeviceSpec(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(session: AsyncSession, db_obj: DeviceSpec, data: dict) -> DeviceSpec:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: DeviceSpec) -> None:
        await session.delete(db_obj)
        await session.commit()

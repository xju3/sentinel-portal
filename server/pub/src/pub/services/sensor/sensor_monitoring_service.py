"""
Device service - business logic for device operations
"""

import asyncio
import logging
from datetime import datetime, timezone
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
from pub.models.sensor import Sensor, SensorMonitoring
from pub.models.customer import HealthCheckFreq
from pub.utils.sorting import apply_sorting

logger = logging.getLogger(__name__)


BINDING_FIELDS = (
    "device_inst_id",
    "location_id",
    "sensor_id",
    "direction",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

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
        payload = dict(data)
        payload["status"] = int(payload.get("status", 1))
        if payload["status"] != 1:
            raise ValueError("A new monitoring binding must be active")
        SensorMonitoringService._validate_binding_payload(payload)
        await SensorMonitoringService._ensure_active_binding_available(
            session,
            payload,
        )
        db_obj = SensorMonitoring(
            **payload,
            bound_at=_utc_now(),
            unbound_at=None,
        )
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        await SensorMonitoringService._notify_binding_sensors(
            session,
            {db_obj.sensor_id},
            {db_obj.device_inst_id},
        )
        return db_obj

    @staticmethod
    async def update(session: AsyncSession, db_obj, data: dict):
        """Close the old binding and create a new version when it changes."""
        desired = {
            field: data.get(field, getattr(db_obj, field))
            for field in BINDING_FIELDS
        }
        desired_status = int(data.get("status", db_obj.status))
        binding_changed = any(
            desired[field] != getattr(db_obj, field)
            for field in BINDING_FIELDS
        )

        if int(db_obj.status) != 1:
            if desired_status != 1:
                if binding_changed:
                    raise ValueError("Historical monitoring bindings are read-only")
                return db_obj
            return await SensorMonitoringService._create_replacement(
                session=session,
                old_binding=db_obj,
                payload=desired,
            )

        if not binding_changed:
            if desired_status == 1:
                return db_obj
            await SensorMonitoringService._close_binding(session, db_obj)
            await SensorMonitoringService._notify_binding_sensors(
                session,
                {db_obj.sensor_id},
                {db_obj.device_inst_id},
            )
            return db_obj

        await SensorMonitoringService._close_binding(session, db_obj, commit=False)
        if desired_status != 1:
            await session.commit()
            await session.refresh(db_obj)
            await SensorMonitoringService._notify_binding_sensors(
                session,
                {db_obj.sensor_id},
                {db_obj.device_inst_id},
            )
            return db_obj

        replacement = await SensorMonitoringService._create_replacement(
            session=session,
            old_binding=db_obj,
            payload=desired,
        )
        return replacement

    @staticmethod
    async def delete(session: AsyncSession, db_obj) -> None:
        """End an active binding; historical binding rows are never deleted."""
        if int(db_obj.status) != 1:
            return
        await SensorMonitoringService._close_binding(session, db_obj)
        await SensorMonitoringService._notify_binding_sensors(
            session,
            {db_obj.sensor_id},
            {db_obj.device_inst_id},
        )

    @staticmethod
    async def _create_replacement(
        session: AsyncSession,
        old_binding: SensorMonitoring,
        payload: dict,
    ) -> SensorMonitoring:
        SensorMonitoringService._validate_binding_payload(payload)
        await session.flush()
        await SensorMonitoringService._ensure_active_binding_available(
            session,
            payload,
            exclude_id=old_binding.id,
        )
        replacement = SensorMonitoring(
            **payload,
            status=1,
            bound_at=_utc_now(),
            unbound_at=None,
        )
        session.add(replacement)
        await session.commit()
        await session.refresh(old_binding)
        await session.refresh(replacement)
        await SensorMonitoringService._notify_binding_sensors(
            session,
            {old_binding.sensor_id, replacement.sensor_id},
            {old_binding.device_inst_id, replacement.device_inst_id},
        )
        return replacement

    @staticmethod
    async def _close_binding(
        session: AsyncSession,
        db_obj: SensorMonitoring,
        *,
        commit: bool = True,
    ) -> None:
        db_obj.status = 0
        db_obj.unbound_at = _utc_now()
        if commit:
            await session.commit()
            await session.refresh(db_obj)

    @staticmethod
    async def _ensure_active_binding_available(
        session: AsyncSession,
        payload: dict,
        exclude_id: UUID | None = None,
    ) -> None:
        conflicts = []
        sensor_id = payload.get("sensor_id")
        device_inst_id = payload.get("device_inst_id")
        location_id = payload.get("location_id")
        if sensor_id is not None:
            conflicts.append(SensorMonitoring.sensor_id == sensor_id)
        if device_inst_id is not None and location_id is not None:
            conflicts.append(
                (SensorMonitoring.device_inst_id == device_inst_id)
                & (SensorMonitoring.location_id == location_id)
            )
        if not conflicts:
            return

        statement = select(SensorMonitoring).where(
            SensorMonitoring.status == 1,
            or_(*conflicts),
        )
        if exclude_id is not None:
            statement = statement.where(SensorMonitoring.id != exclude_id)
        existing = (await session.execute(statement)).scalars().first()
        if existing is None:
            return
        if sensor_id is not None and existing.sensor_id == sensor_id:
            raise ValueError("Sensor already has an active monitoring binding")
        raise ValueError("Device monitoring point already has an active sensor binding")

    @staticmethod
    def _validate_binding_payload(payload: dict) -> None:
        if payload.get("location_id") is None:
            raise ValueError("Monitoring point is required for a sensor binding")
        if payload.get("sensor_id") is None:
            raise ValueError("Sensor is required for a monitoring point binding")

    @staticmethod
    async def _notify_binding_sensors(
        session: AsyncSession,
        sensor_ids: set[UUID | None],
        device_ids: set[UUID | None],
    ) -> None:
        active_sensor_ids = {item for item in sensor_ids if item is not None}
        affected_device_ids = {item for item in device_ids if item is not None}
        if not active_sensor_ids and not affected_device_ids:
            return

        sns: list[str] = []
        if active_sensor_ids:
            sns = list(
                (
                    await session.execute(
                        select(Sensor.sn).where(Sensor.id.in_(active_sensor_ids))
                    )
                )
                .scalars()
                .all()
            )

        peer_groups: list[tuple[UUID, UUID]] = []
        if affected_device_ids:
            peer_groups = [
                (process_device_id, device_category_id)
                for process_device_id, device_category_id in (
                    await session.execute(
                        select(
                            ProcessDeviceItem.process_device_id,
                            DeviceSpec.device_category_id,
                        )
                        .select_from(DeviceInst)
                        .join(DeviceSpec, DeviceSpec.id == DeviceInst.device_spec_id)
                        .outerjoin(
                            ProcessDeviceItem,
                            ProcessDeviceItem.device_inst_id == DeviceInst.id,
                        )
                        .where(DeviceInst.id.in_(affected_device_ids))
                    )
                ).all()
                if process_device_id is not None and device_category_id is not None
            ]

        from pub.manager.database import redis_manager
        from pub.utils.redis_keys import (
            REDIS_KEY_DIA_DEVICE_CONTEXT,
            REDIS_KEY_DIA_DIAGNOSIS_CONTEXT,
            REDIS_KEY_DIA_PEER_GROUP,
            REDIS_KEY_SENSOR_META,
        )

        cache_keys = {
            REDIS_KEY_SENSOR_META.format(sn=sn)
            for sn in sns
        }
        cache_keys.update(
            REDIS_KEY_DIA_DIAGNOSIS_CONTEXT.format(sn=sn)
            for sn in sns
        )
        cache_keys.update(
            REDIS_KEY_DIA_DEVICE_CONTEXT.format(device_id=device_id)
            for device_id in affected_device_ids
        )
        cache_keys.update(
            REDIS_KEY_DIA_PEER_GROUP.format(
                process_device_id=process_device_id,
                device_category_id=device_category_id,
            )
            for process_device_id, device_category_id in peer_groups
        )

        if cache_keys:
            try:
                redis_client = redis_manager.get_client()
                await asyncio.to_thread(
                    redis_client.delete,
                    *sorted(cache_keys),
                )
            except RuntimeError:
                pass
            except Exception:
                logger.exception(
                    "Failed to invalidate binding caches for sns=%s device_ids=%s",
                    sns,
                    sorted(str(item) for item in affected_device_ids),
                )

        from pub.services.sensor.sensor_task_service import (
            SYSTEM_ACTION_UPDATE_BINDING,
            create_manual_sensor_task,
        )

        for sensor_id in active_sensor_ids:
            try:
                await create_manual_sensor_task(
                    session=session,
                    sensor_id=sensor_id,
                    name="update_binding",
                    action=SYSTEM_ACTION_UPDATE_BINDING,
                    val=0,
                    remark="Monitoring binding changed",
                )
            except Exception:
                logger.exception(
                    "Failed to create binding update task for sensor_id=%s",
                    sensor_id,
                )


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

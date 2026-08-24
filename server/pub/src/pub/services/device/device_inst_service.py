"""
Device service - business logic for device operations
"""

from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import case, exists, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from pub.models.customer import Location
from pub.models.device import (
    DeviceCategory,
    DeviceInst,
    DeviceSpec,
    Process,
    ProcessDevice,
    ProcessDeviceItem,
)
from pub.models.sensor import SensorMonitoring
from pub.utils.sorting import apply_sorting


class DeviceInstService:
    @staticmethod
    def _health_archive_monitored_devices(tenant_id: UUID):
        return (
            select(
                SensorMonitoring.device_inst_id.label("device_id"),
                func.count(
                    func.distinct(
                        case(
                            (SensorMonitoring.status == 1, SensorMonitoring.id),
                            else_=None,
                        )
                    )
                ).label("active_binding_count"),
                func.count(
                    func.distinct(SensorMonitoring.location_id)
                ).label("historical_point_count"),
                func.max(
                    func.coalesce(
                        SensorMonitoring.unbound_at,
                        SensorMonitoring.bound_at,
                    )
                ).label("last_monitored_at"),
            )
            .join(Location, Location.id == SensorMonitoring.location_id)
            .where(
                SensorMonitoring.sensor_id.is_not(None),
                Location.tenant_id == tenant_id,
            )
            .group_by(SensorMonitoring.device_inst_id)
            .subquery()
        )

    @staticmethod
    async def get_all(
        session: AsyncSession,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[DeviceInst]:
        stmt = select(DeviceInst)
        stmt = apply_sorting(stmt, DeviceInst, sort_by, sort_order or "ascend")
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_by_id(session: AsyncSession, obj_id: UUID) -> Optional[DeviceInst]:
        stmt = select(DeviceInst).where(DeviceInst.id == obj_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def is_tenant_device_inst(
        session: AsyncSession,
        tenant_id: UUID,
        device_inst_id: UUID,
    ) -> bool:
        stmt = (
            select(DeviceInst.id)
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(
                DeviceInst.id == device_inst_id,
                DeviceCategory.tenant_id == tenant_id,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_tenant_device_insts_paged(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        keyword: Optional[str] = None,
        name: Optional[str] = None,
        code: Optional[str] = None,
        purchase_date: Optional[str] = None,
        life_span: Optional[int] = None,
        desc: Optional[str] = None,
        status: Optional[int] = None,
        device_spec_id: Optional[UUID] = None,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> tuple:
        """Get paged DeviceInsts scoped to tenant, with total count."""
        base_join = (
            select(DeviceInst)
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(DeviceCategory.tenant_id == tenant_id)
        )
        if keyword:
            like = f"%{keyword.strip()}%"
            base_join = base_join.where(
                or_(
                    DeviceInst.name.ilike(like),
                    DeviceInst.code.ilike(like),
                    DeviceInst.desc.ilike(like),
                )
            )
        if name:
            base_join = base_join.where(DeviceInst.name.ilike(f"%{name.strip()}%"))
        if code:
            base_join = base_join.where(DeviceInst.code.ilike(f"%{code.strip()}%"))
        if purchase_date:
            base_join = base_join.where(DeviceInst.purchase_date == purchase_date)
        if life_span is not None:
            base_join = base_join.where(DeviceInst.life_span == life_span)
        if desc:
            base_join = base_join.where(DeviceInst.desc.ilike(f"%{desc.strip()}%"))
        if status is not None:
            base_join = base_join.where(DeviceInst.status == status)
        if device_spec_id is not None:
            base_join = base_join.where(DeviceInst.device_spec_id == device_spec_id)

        count_stmt = select(func.count()).select_from(base_join.subquery())
        count_result = await session.execute(count_stmt)
        total = count_result.scalar() or 0

        fetch_stmt = apply_sorting(
            base_join, DeviceInst, sort_by, sort_order or "ascend"
        ).options(
            selectinload(DeviceInst.device_spec).selectinload(DeviceSpec.supplier),
            selectinload(DeviceInst.device_spec).selectinload(
                DeviceSpec.device_category
            ),
            selectinload(DeviceInst.sensor_monitorings).selectinload(
                SensorMonitoring.location
            ),
            selectinload(DeviceInst.sensor_monitorings).selectinload(
                SensorMonitoring.sensor
            ),
        ).offset(skip).limit(limit)
        result = await session.execute(fetch_stmt)
        items = result.scalars().all()

        return items, total

    @staticmethod
    async def get_tenant_health_archive_devices_paged(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        device_category_id: UUID | None = None,
        device_spec_id: UUID | None = None,
        process_device_id: UUID | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        monitored_devices = DeviceInstService._health_archive_monitored_devices(
            tenant_id
        )

        base_stmt = (
            select(
                DeviceInst.id,
                DeviceInst.name,
                DeviceInst.code,
                DeviceInst.desc,
                DeviceInst.status,
                DeviceInst.active,
                DeviceInst.available,
                DeviceSpec.id.label("device_spec_id"),
                DeviceSpec.name.label("device_spec_name"),
                DeviceSpec.model.label("device_spec_model"),
                DeviceSpec.brand.label("device_spec_brand"),
                DeviceCategory.id.label("device_category_id"),
                DeviceCategory.name.label("device_category_name"),
                DeviceCategory.color.label("device_category_color"),
                monitored_devices.c.active_binding_count,
                monitored_devices.c.historical_point_count,
                monitored_devices.c.last_monitored_at,
            )
            .join(monitored_devices, monitored_devices.c.device_id == DeviceInst.id)
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(DeviceCategory.tenant_id == tenant_id)
        )

        if device_category_id is not None:
            selected_categories = (
                select(DeviceCategory.id)
                .where(
                    DeviceCategory.id == device_category_id,
                    DeviceCategory.tenant_id == tenant_id,
                )
                .cte(name="selected_device_categories", recursive=True)
            )
            selected_categories = selected_categories.union_all(
                select(DeviceCategory.id).where(
                    DeviceCategory.parent_id == selected_categories.c.id,
                    DeviceCategory.tenant_id == tenant_id,
                )
            )
            base_stmt = base_stmt.where(
                DeviceCategory.id.in_(select(selected_categories.c.id))
            )
        if device_spec_id is not None:
            base_stmt = base_stmt.where(DeviceSpec.id == device_spec_id)
        if process_device_id is not None:
            belongs_to_group = exists(
                select(ProcessDeviceItem.id)
                .join(
                    ProcessDevice,
                    ProcessDevice.id == ProcessDeviceItem.process_device_id,
                )
                .join(Process, Process.id == ProcessDevice.process_id)
                .where(
                    ProcessDeviceItem.device_inst_id == DeviceInst.id,
                    ProcessDeviceItem.process_device_id == process_device_id,
                    Process.tenant_id == tenant_id,
                )
            )
            base_stmt = base_stmt.where(belongs_to_group)

        base_stmt = base_stmt.order_by(DeviceInst.name.asc(), DeviceInst.id.asc())

        rows = (
            await session.execute(base_stmt.offset(skip).limit(limit + 1))
        ).all()

        has_more = len(rows) > limit
        rows = rows[:limit]

        items = [
            {
                "id": row.id,
                "name": row.name,
                "code": row.code,
                "desc": row.desc,
                "status": row.status,
                "active": row.active,
                "available": row.available,
                "deviceSpec": {
                    "id": row.device_spec_id,
                    "name": row.device_spec_name,
                    "model": row.device_spec_model,
                    "brand": row.device_spec_brand,
                },
                "deviceCategory": {
                    "id": row.device_category_id,
                    "name": row.device_category_name,
                    "color": row.device_category_color,
                },
                "activeBindingCount": row.active_binding_count or 0,
                "historicalPointCount": row.historical_point_count or 0,
                "lastMonitoredAt": row.last_monitored_at,
            }
            for row in rows
        ]
        return items, has_more

    @staticmethod
    async def get_tenant_health_archive_device_filters(
        session: AsyncSession,
        tenant_id: UUID,
    ) -> dict[str, list[dict[str, Any]]]:
        monitored_devices = DeviceInstService._health_archive_monitored_devices(
            tenant_id
        )
        monitored_join = (
            select(DeviceInst.id)
            .join(
                monitored_devices,
                monitored_devices.c.device_id == DeviceInst.id,
            )
            .subquery()
        )

        category_stmt = (
            select(
                DeviceCategory.id,
                DeviceCategory.name,
                DeviceCategory.parent_id,
            )
            .where(DeviceCategory.tenant_id == tenant_id)
            .order_by(DeviceCategory.name.asc(), DeviceCategory.id.asc())
        )
        spec_stmt = (
            select(
                DeviceSpec.id,
                DeviceSpec.name,
                DeviceSpec.device_category_id,
            )
            .join(DeviceInst, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(monitored_join, monitored_join.c.id == DeviceInst.id)
            .join(
                DeviceCategory,
                DeviceCategory.id == DeviceSpec.device_category_id,
            )
            .where(DeviceCategory.tenant_id == tenant_id)
            .distinct()
            .order_by(DeviceSpec.name.asc(), DeviceSpec.id.asc())
        )
        group_stmt = (
            select(
                ProcessDevice.id,
                ProcessDevice.code,
                Process.name.label("process_name"),
                DeviceInst.device_spec_id,
            )
            .join(
                ProcessDeviceItem,
                ProcessDeviceItem.process_device_id == ProcessDevice.id,
            )
            .join(DeviceInst, DeviceInst.id == ProcessDeviceItem.device_inst_id)
            .join(monitored_join, monitored_join.c.id == DeviceInst.id)
            .join(Process, Process.id == ProcessDevice.process_id)
            .join(DeviceSpec, DeviceSpec.id == DeviceInst.device_spec_id)
            .join(
                DeviceCategory,
                DeviceCategory.id == DeviceSpec.device_category_id,
            )
            .where(
                Process.tenant_id == tenant_id,
                DeviceCategory.tenant_id == tenant_id,
            )
            .distinct()
            .order_by(Process.name.asc(), ProcessDevice.code.asc(), ProcessDevice.id.asc())
        )

        category_rows = (await session.execute(category_stmt)).all()
        spec_rows = (await session.execute(spec_stmt)).all()
        group_rows = (await session.execute(group_stmt)).all()
        category_by_id = {row.id: row for row in category_rows}
        visible_category_ids = {row.device_category_id for row in spec_rows}
        pending_category_ids = list(visible_category_ids)
        while pending_category_ids:
            category_id = pending_category_ids.pop()
            category = category_by_id.get(category_id)
            parent_id = category.parent_id if category is not None else None
            if parent_id is not None and parent_id not in visible_category_ids:
                visible_category_ids.add(parent_id)
                pending_category_ids.append(parent_id)

        groups: dict[UUID, dict[str, Any]] = {}
        for row in group_rows:
            group = groups.setdefault(
                row.id,
                {
                    "id": row.id,
                    "name": row.process_name or row.code,
                    "deviceSpecIds": [],
                },
            )
            if row.device_spec_id not in group["deviceSpecIds"]:
                group["deviceSpecIds"].append(row.device_spec_id)

        return {
            "categories": [
                {
                    "id": row.id,
                    "name": row.name,
                    "parentId": row.parent_id,
                }
                for row in category_rows
                if row.id in visible_category_ids
            ],
            "specs": [
                {
                    "id": row.id,
                    "name": row.name,
                    "deviceCategoryId": row.device_category_id,
                }
                for row in spec_rows
            ],
            "groups": list(groups.values()),
        }

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> DeviceInst:
        db_obj = DeviceInst(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(session: AsyncSession, db_obj: DeviceInst, data: dict) -> DeviceInst:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: DeviceInst) -> None:
        await session.delete(db_obj)
        await session.commit()


def generate_standard_service(model_class):
    """Factory class to generate basic CRUD services to avoid excessive boilerplate"""

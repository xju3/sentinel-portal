"""
Device service - business logic for device operations
"""

from uuid import UUID
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import case, func, or_

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
from pub.models.customer import HealthCheckFreq, Location
from pub.utils.sorting import apply_sorting

class DeviceInstService:
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
        current: int,
        page_size: int,
        keyword: Optional[str] = None,
    ) -> tuple:
        """Get paged DeviceInsts scoped to tenant, with total count."""
        from pub.models.customer import Location as LocationModel

        base_join = (
            select(DeviceInst)
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(DeviceCategory.tenant_id == tenant_id)
        )
        if keyword:
            like = f"%{keyword}%"
            base_join = base_join.where(
                or_(DeviceInst.name.ilike(like), DeviceInst.code.ilike(like))
            )

        count_stmt = select(func.count()).select_from(base_join.subquery())
        count_result = await session.execute(count_stmt)
        total = count_result.scalar() or 0

        skip = (current - 1) * page_size
        fetch_stmt = base_join.offset(skip).limit(page_size)
        result = await session.execute(fetch_stmt)
        items = result.scalars().all()

        return items, total

    @staticmethod
    async def get_tenant_health_archive_devices_paged(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        monitored_devices = (
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
            .order_by(DeviceInst.name.asc(), DeviceInst.id.asc())
        )

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

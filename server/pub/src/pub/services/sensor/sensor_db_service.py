"""
Sensor service - business logic for sensor operations
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.query_api import QueryApi

from pub.manager.database import influxdb_manager, db_manager
from fastapi import BackgroundTasks
from pub.models.sensor import SensorType, Sensor, SensorBatch, SensorThreshold, SensorMonitoring, SimCard
from pub.models.device import DeviceInst, DeviceSpec, DeviceCategory, ProcessDeviceItem, ProcessDevice
from pub.models.customer import Tenant, Area, HealthCheckFreq, IsoStandard, Region
from pub.exceptions.domain_exception import DomainException
from pub.utils.sorting import apply_sorting
logger = logging.getLogger(__name__)

class SensorDbService:
    @staticmethod
    async def get_all(
        session: AsyncSession,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[Sensor]:
        stmt = select(Sensor)
        stmt = apply_sorting(stmt, Sensor, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(session: AsyncSession, obj_id: UUID) -> Optional[Sensor]:
        stmt = select(Sensor).where(Sensor.id == obj_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_binding_by_sn(session: AsyncSession, sn: str) -> Optional[UUID]:
        from pub.models.sensor import SensorMonitoring
        from sqlalchemy import and_
        stmt = (
            select(SensorMonitoring.device_inst_id)
            .join(Sensor, Sensor.id == SensorMonitoring.sensor_id)
            .where(
                and_(
                    Sensor.sn == sn,
                    SensorMonitoring.status == 1
                )
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_sensor_metadata_for_cache(session: AsyncSession, sn: str) -> Optional[dict]:
        from pub.models.sensor import SensorMonitoring
        from pub.models.device import DeviceInst, DeviceSpec, DeviceCategory, ProcessDeviceItem
        from pub.models.customer import Tenant
        from sqlalchemy import and_

        stmt = (
            select(
                Sensor.id.label("sensor_id"),
                Sensor.sn.label("sensor_sn"),
                SensorMonitoring.device_inst_id.label("device_id"),
                SensorMonitoring.location_id,
                DeviceCategory.tenant_id,
                Tenant.region_id,
                DeviceSpec.device_category_id,
                ProcessDeviceItem.process_device_id,
            )
            .join(SensorMonitoring, Sensor.id == SensorMonitoring.sensor_id)
            .outerjoin(DeviceInst, SensorMonitoring.device_inst_id == DeviceInst.id)
            .outerjoin(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .outerjoin(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .outerjoin(Tenant, DeviceCategory.tenant_id == Tenant.id)
            .outerjoin(ProcessDeviceItem, ProcessDeviceItem.device_inst_id == DeviceInst.id)
            .where(
                and_(
                    Sensor.sn == sn,
                    SensorMonitoring.status == 1
                )
            )
        )
        result = await session.execute(stmt)
        row = result.first()
        if not row:
            return None
        
        return {
            "sensor_id": str(row.sensor_id) if row.sensor_id else None,
            "sensor_sn": row.sensor_sn,
            "device_id": str(row.device_id) if row.device_id else None,
            "location_id": str(row.location_id) if row.location_id else None,
            "tenant_id": str(row.tenant_id) if row.tenant_id else None,
            "region_id": row.region_id,
            "device_category_id": str(row.device_category_id) if row.device_category_id else None,
            "process_device_id": str(row.process_device_id) if row.process_device_id else None,
        }

    @classmethod
    async def get_sensor_metadata_for_cache_managed(cls, sn: str) -> Optional[dict]:
        from pub.manager.database import db_manager
        async with db_manager.session_maker() as session:
            return await cls.get_sensor_metadata_for_cache(session, sn)

    @staticmethod
    async def get_by_batch_id(
        session: AsyncSession, 
        batch_id: UUID, 
        skip: int = 0, 
        limit: int = 100,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[Sensor]:
        stmt = (
            select(Sensor)
            .where(Sensor.sensor_batch_id == batch_id)
        )
        stmt = apply_sorting(stmt, Sensor, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_paged(
        session: AsyncSession,
        current: int,
        page_size: int,
        keyword: Optional[str] = None,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> tuple:
        """Get paged sensors with total count. Returns (items, total)."""
        from sqlalchemy import func

        base_stmt = select(Sensor)
        
        if not sort_by:
            sort_by = "sn"
            if sort_order == "ascend":
                sort_order = "descend"
                
        base_stmt = apply_sorting(base_stmt, Sensor, sort_by, sort_order)
        if keyword:
            like = f"%{keyword}%"
            base_stmt = base_stmt.where(Sensor.sn.ilike(like))

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        count_result = await session.execute(count_stmt)
        total = count_result.scalar() or 0

        skip = (current - 1) * page_size
        fetch_stmt = base_stmt.offset(skip).limit(page_size)
        result = await session.execute(fetch_stmt)
        items = list(result.scalars().all())

        if items:
            from pub.models.sensor import SensorStatus
            from sqlalchemy import and_

            sns = [item.sn for item in items]
            subq = (
                select(SensorStatus.sn, func.max(SensorStatus.ts).label("max_ts"))
                .where(SensorStatus.sn.in_(sns))
                .group_by(SensorStatus.sn)
                .subquery()
            )
            status_stmt = select(SensorStatus).join(
                subq, and_(SensorStatus.sn == subq.c.sn, SensorStatus.ts == subq.c.max_ts)
            )
            statuses = await session.execute(status_stmt)
            status_map = {s.sn: s for s in statuses.scalars().all()}
            for item in items:
                item.latest_status = status_map.get(item.sn)

        return items, total

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> Sensor:
        db_obj = Sensor(**data)
        session.add(db_obj)

        # 绑定 SIM 卡时，自动更新激活时间和状态
        if db_obj.sim_id:
            sim_card = await session.get(SimCard, db_obj.sim_id)
            if sim_card:
                sim_card.bound = 1
                if sim_card.activated_at is None:
                    sim_card.activated_at = datetime.utcnow()
                    sim_card.status = 1

        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def create_batch(session: AsyncSession, items: List[dict]) -> List[Sensor]:
        """批量创建 Sensor 记录"""
        db_objs = [Sensor(**item) for item in items]
        session.add_all(db_objs)
        await session.commit()
        for obj in db_objs:
            await session.refresh(obj)
        return db_objs

    @staticmethod
    async def update(session: AsyncSession, db_obj: Sensor, data: dict) -> Sensor:
        old_sim_id = db_obj.sim_id

        for key, value in data.items():
            setattr(db_obj, key, value)

        new_sim_id = db_obj.sim_id

        # 解绑旧 SIM 卡
        if old_sim_id and old_sim_id != new_sim_id:
            old_sim = await session.get(SimCard, old_sim_id)
            if old_sim:
                old_sim.bound = 0

        # 绑定新 SIM 卡
        if new_sim_id and new_sim_id != old_sim_id:
            sim_card = await session.get(SimCard, new_sim_id)
            if sim_card:
                sim_card.bound = 1
                if sim_card.activated_at is None:
                    sim_card.activated_at = datetime.utcnow()
                    sim_card.status = 1

        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: Sensor) -> None:
        await session.delete(db_obj)
        await session.commit()

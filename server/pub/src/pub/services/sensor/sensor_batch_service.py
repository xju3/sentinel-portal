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
from pub.services.sensor.sensor_db_service import SensorDbService

logger = logging.getLogger(__name__)

class SensorBatchService:
    @staticmethod
    async def get_all(
        session: AsyncSession,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[SensorBatch]:
        stmt = select(SensorBatch)
        stmt = apply_sorting(stmt, SensorBatch, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(session: AsyncSession, obj_id: UUID) -> Optional[SensorBatch]:
        stmt = select(SensorBatch).where(SensorBatch.id == obj_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

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
    async def get_by_id_and_tenant(session: AsyncSession, obj_id: UUID, tenant_id: UUID) -> Optional[SensorBatch]:
        stmt = select(SensorBatch).where(
            SensorBatch.id == obj_id,
            SensorBatch.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> SensorBatch:
        db_obj = SensorBatch(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(session: AsyncSession, db_obj: SensorBatch, data: dict, background_tasks: BackgroundTasks) -> SensorBatch:
        # Status 只能向前递增，不能回退
        if "status" in data:
            if data["status"] < db_obj.status:
                raise DomainException(
                    code=400,
                    message=f"Status cannot be decreased from {db_obj.status} to {data['status']}",
                )

            # 当 status 从 1（生产中）→ 2（交付中）时，自动异步生成该批次的传感器数据
            if db_obj.status == 1 and data["status"] == 2: # type: ignore
                existing_sensors = await SensorDbService.get_by_batch_id(session, db_obj.id)
                if not existing_sensors:
                    background_tasks.add_task(SensorBatchService.generate_sensors_for_batch, db_obj.id)
                    logger.info(f"Queued background task to generate sensors for batch {db_obj.code} (id={db_obj.id})")

        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: SensorBatch) -> None:
        await session.delete(db_obj)
        await session.commit()

    @staticmethod
    async def generate_sensors_for_batch(batch_id: UUID) -> None:
        """
        后台异步生成该批次对应的传感器数据。
        
        规则：
        - sensor_batch_id = 当前批次的 ID
        - sn = 批次 sn 值（前缀） + 5位流水号（从 region.cnt+1 开始，至 qty 数量为止）
        - active = False (0)
        - active_at = None
        """
        async with db_manager.SessionLocal() as session:
            try:
                batch = await session.get(SensorBatch, batch_id)
                if not batch:
                    logger.error(f"Generate sensors failed: batch {batch_id} not found")
                    return
                
                tenant = await session.get(Tenant, batch.tenant_id)
                if not tenant:
                    logger.error(f"Generate sensors failed: tenant for batch {batch_id} not found")
                    return

                # 使用 for update 行锁来保证 cnt 的并发安全
                stmt = select(Region).where(Region.id == tenant.region_id).with_for_update()
                result = await session.execute(stmt)
                region = result.scalar_one_or_none()
                if not region:
                    logger.error(f"Generate sensors failed: region for tenant {tenant.id} not found")
                    return

                sn_prefix = str(batch.sn)  # e.g. 26SH
                qty = int(batch.qty)
                start_seq = (region.cnt or 0) + 1

                items = []
                for i in range(qty):
                    seq = start_seq + i
                    sn = f"{sn_prefix}{seq:05d}"
                    items.append({
                        "sn": sn,
                        "active": False,
                        "active_at": None,
                        "sensor_batch_id": batch.id,
                    })

                # 批量生成传感器
                await SensorDbService.create_batch(session, items)
                
                # 更新 region 的 cnt
                region.cnt = (region.cnt or 0) + qty
                session.add(region)
                await session.commit()
                logger.info(f"Successfully generated {qty} sensors for batch {batch.code}")
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to generate sensors for batch {batch_id}: {e}")

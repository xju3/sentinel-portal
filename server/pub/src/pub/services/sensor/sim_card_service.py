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

class SimCardService:
    @staticmethod
    async def get_paged(
        session: AsyncSession,
        current: int,
        page_size: int,
        keyword: Optional[str] = None,
        status: Optional[int] = None,
        unbound_only: bool = False,
        unactivated_only: bool = False,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> tuple:
        from sqlalchemy import func
        from pub.models.sensor import Sensor

        base_stmt = select(SimCard)
        base_stmt = apply_sorting(base_stmt, SimCard, sort_by, sort_order)
        
        if keyword:
            like = f"%{keyword}%"
            base_stmt = base_stmt.where(
                (SimCard.ccid.ilike(like)) | (SimCard.carrier.ilike(like))
            )
            
        if status is not None:
            base_stmt = base_stmt.where(SimCard.status == status)
            
        if unbound_only:
            # 左连接 Sensor 表，筛选出尚未绑定任何传感器的 SIM 卡
            base_stmt = base_stmt.outerjoin(Sensor, Sensor.sim_id == SimCard.id).where(Sensor.id.is_(None))
            
        if unactivated_only:
            base_stmt = base_stmt.where(SimCard.activated_at.is_(None))

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        count_result = await session.execute(count_stmt)
        total = count_result.scalar() or 0

        skip = (current - 1) * page_size
        fetch_stmt = base_stmt.offset(skip).limit(page_size)
        result = await session.execute(fetch_stmt)
        items = list(result.scalars().all())

        return items, total

    @staticmethod
    async def get_by_id(session: AsyncSession, obj_id: UUID) -> Optional[SimCard]:
        stmt = select(SimCard).where(SimCard.id == obj_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> SimCard:
        db_obj = SimCard(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(session: AsyncSession, db_obj: SimCard, data: dict) -> SimCard:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: SimCard) -> None:
        await session.delete(db_obj)
        await session.commit()

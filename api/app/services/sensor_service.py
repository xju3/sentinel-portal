"""
Sensor service - business logic for sensor operations
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.query_api import QueryApi

from app.database import influxdb_manager
from app.config import settings
from app.models.sensor import SensorType, Sensor, SensorBatch, SensorThreshold

logger = logging.getLogger(__name__)


class SensorTypeService:
    @staticmethod
    async def get_all(session: AsyncSession, skip: int, limit: int) -> List[SensorType]:
        stmt = select(SensorType).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_by_id(session: AsyncSession, obj_id: UUID) -> Optional[SensorType]:
        stmt = select(SensorType).where(SensorType.id == obj_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> SensorType:
        db_obj = SensorType(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(session: AsyncSession, db_obj: SensorType, data: dict) -> SensorType:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: SensorType) -> None:
        await session.delete(db_obj)
        await session.commit()


class SensorDbService:
    @staticmethod
    async def get_all(session: AsyncSession, skip: int, limit: int) -> List[Sensor]:
        stmt = select(Sensor).offset(skip).order_by(Sensor.sn).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_by_id(session: AsyncSession, obj_id: UUID) -> Optional[Sensor]:
        stmt = select(Sensor).where(Sensor.id == obj_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_batch_id(session: AsyncSession, batch_id: UUID, skip: int = 0, limit: int = 100) -> List[Sensor]:
        stmt = (
            select(Sensor)
            .where(Sensor.sensor_batch_id == batch_id)
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_paged(
        session: AsyncSession,
        current: int,
        page_size: int,
        keyword: Optional[str] = None,
    ) -> tuple:
        """Get paged sensors with total count. Returns (items, total)."""
        from sqlalchemy import func

        base_stmt = select(Sensor).order_by(Sensor.sn)
        if keyword:
            like = f"%{keyword}%"
            base_stmt = base_stmt.where(Sensor.sn.ilike(like))

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        count_result = await session.execute(count_stmt)
        total = count_result.scalar() or 0

        skip = (current - 1) * page_size
        fetch_stmt = base_stmt.offset(skip).limit(page_size)
        result = await session.execute(fetch_stmt)
        items = result.scalars().all()

        return items, total

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> Sensor:
        db_obj = Sensor(**data)
        session.add(db_obj)
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
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: Sensor) -> None:
        await session.delete(db_obj)
        await session.commit()



class SensorBatchService:
    @staticmethod
    async def get_all(session: AsyncSession, skip: int, limit: int) -> List[SensorBatch]:
        stmt = select(SensorBatch).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_by_id(session: AsyncSession, obj_id: UUID) -> Optional[SensorBatch]:
        stmt = select(SensorBatch).where(SensorBatch.id == obj_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_tenant(session: AsyncSession, tenant_id: UUID, skip: int, limit: int) -> List[SensorBatch]:
        stmt = (
            select(SensorBatch)
            .where(SensorBatch.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

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
    async def update(session: AsyncSession, db_obj: SensorBatch, data: dict) -> SensorBatch:
        # Status 只能向前递增，不能回退
        if "status" in data:
            if data["status"] < db_obj.status:
                raise ValueError(
                    f"Status cannot be decreased from {db_obj.status} to {data['status']}"
                )

            # 当 status 从 1（生产中）→ 2（交付中）时，自动生成该批次的传感器数据
            if db_obj.status == 1 and data["status"] == 2:
                existing_sensors = await SensorDbService.get_by_batch_id(session, db_obj.id)
                if not existing_sensors:
                    await SensorBatchService.generate_sensors_for_batch(session, db_obj)
                    logger.info(f"Generated sensors for batch {db_obj.code} (id={db_obj.id})")

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
    async def generate_sensors_for_batch(session: AsyncSession, batch: SensorBatch) -> List[Sensor]:
        """
        当批次状态变为 2（交付中）时，生成该批次对应的传感器数据。
        
        规则：
        - sensor_batch_id = 当前批次的 ID
        - sn = 批次 sn 值 + 下三位流水号（从 001 开始，至 qty 数量为止）
        - active = False (0)
        - active_at = None
        """
        sn_prefix = batch.sn
        qty = batch.qty

        items = []
        for i in range(1, qty + 1):
            sn = f"{sn_prefix}{i:03d}"
            items.append({
                "sn": sn,
                "active": False,
                "active_at": None,
                "sensor_batch_id": batch.id,
            })

        return await SensorDbService.create_batch(session, items)



class SensorThresholdService:
    @staticmethod
    async def get_by_tenant(session: AsyncSession, tenant_id: UUID, skip: int, limit: int) -> List[SensorThreshold]:
        stmt = (
            select(SensorThreshold)
            .where(SensorThreshold.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_by_id_and_tenant(session: AsyncSession, obj_id: UUID, tenant_id: UUID) -> Optional[SensorThreshold]:
        stmt = select(SensorThreshold).where(
            SensorThreshold.id == obj_id,
            SensorThreshold.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> SensorThreshold:
        db_obj = SensorThreshold(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(session: AsyncSession, db_obj: SensorThreshold, data: dict) -> SensorThreshold:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: SensorThreshold) -> None:
        await session.delete(db_obj)
        await session.commit()


class SensorService:
    """Service for sensor operations"""

    @staticmethod
    def get_latest_reading(sensor_id: int) -> Optional[dict]:
        """
        Get the latest reading for a sensor
        
        Args:
            sensor_id: Sensor ID
            
        Returns:
            Latest reading or None
        """
        try:
            client = influxdb_manager.get_client()
            query_api = client.query_api(query_type="pandas")

            query = f'''
                from(bucket:"{settings.influx_bucket}")
                |> range(start: -1000d)
                |> filter(fn: (r) => r._measurement == "sensor_reading")
                |> filter(fn: (r) => r.sensor_id == "{sensor_id}")
                |> last()
            '''

            result = query_api.query(org=settings.influx_org, query=query)

            for table in result:
                for record in table.records:
                    return {
                        "timestamp": record.get_time(),
                        "value": record.get_value(),
                        "unit": record.values.get("unit"),
                    }

            return None
        except Exception as e:
            logger.error(f"Failed to get latest reading: {e}")
            return None

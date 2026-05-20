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
from app.models.sensor import SensorType, Sensor, SensorBatch

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



class SensorService:
    """Service for sensor operations"""

    @staticmethod
    def write_sensor_data(
        sensor_id: int,
        value: float,
        unit: str = "C",
        timestamp: Optional[datetime] = None,
    ) -> bool:
        """
        Write sensor reading to InfluxDB
        
        Args:
            sensor_id: Sensor ID
            value: Reading value
            unit: Unit of measurement
            timestamp: Reading timestamp (default: now)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            client = influxdb_manager.get_client()
            write_api = client.write_api(write_options=SYNCHRONOUS)

            if timestamp is None:
                timestamp = datetime.utcnow()

            point = (
                f"sensor_reading,sensor_id={sensor_id},unit={unit} "
                f"value={value} {int(timestamp.timestamp() * 1e9)}"
            )

            write_api.write(
                bucket=settings.influx_bucket,
                org=settings.influx_org,
                write_precision="ns",
                record=point,
            )
            logger.info(f"Wrote sensor data: sensor_id={sensor_id}, value={value}")
            return True
        except Exception as e:
            logger.error(f"Failed to write sensor data: {e}")
            return False

    @staticmethod
    def get_sensor_readings(
        sensor_id: int,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> list:
        """
        Query sensor readings from InfluxDB
        
        Args:
            sensor_id: Sensor ID
            start_time: Query start time (default: 24 hours ago)
            end_time: Query end time (default: now)
            
        Returns:
            List of sensor readings
        """
        try:
            if start_time is None:
                start_time = datetime.utcnow() - timedelta(hours=24)
            if end_time is None:
                end_time = datetime.utcnow()

            client = influxdb_manager.get_client()
            query_api = client.query_api(query_type="pandas")

            query = f'''
                from(bucket:"{settings.influx_bucket}")
                |> range(start: {start_time.isoformat()}Z, stop: {end_time.isoformat()}Z)
                |> filter(fn: (r) => r._measurement == "sensor_reading")
                |> filter(fn: (r) => r.sensor_id == "{sensor_id}")
            '''

            result = query_api.query(org=settings.influx_org, query=query)

            readings = []
            for table in result:
                for record in table.records:
                    readings.append({
                        "timestamp": record.get_time(),
                        "value": record.get_value(),
                        "unit": record.values.get("unit"),
                    })

            logger.info(f"Retrieved {len(readings)} readings for sensor {sensor_id}")
            return readings
        except Exception as e:
            logger.error(f"Failed to query sensor readings: {e}")
            return []

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

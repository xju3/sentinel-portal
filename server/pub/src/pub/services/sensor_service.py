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


class SensorTypeService:
    @staticmethod
    async def get_all(
        session: AsyncSession,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> List[SensorType]:
        stmt = select(SensorType)
        stmt = apply_sorting(stmt, SensorType, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

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
            if sim_card and sim_card.activated_at is None:
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

        # 如果更换或新绑定了 SIM 卡，自动更新激活时间和状态
        new_sim_id = db_obj.sim_id
        if new_sim_id and new_sim_id != old_sim_id:
            sim_card = await session.get(SimCard, new_sim_id)
            if sim_card and sim_card.activated_at is None:
                sim_card.activated_at = datetime.utcnow()
                sim_card.status = 1

        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: Sensor) -> None:
        await session.delete(db_obj)
        await session.commit()


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



class SensorThresholdService:
    @staticmethod
    async def get_by_tenant(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
    ) -> Sequence[SensorThreshold]:
        stmt = (
            select(SensorThreshold)
            .where(SensorThreshold.tenant_id == tenant_id)
        )
        stmt = apply_sorting(stmt, SensorThreshold, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
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
                from(bucket:"{influxdb_manager.bucket}")
                |> range(start: -1000d)
                |> filter(fn: (r) => r._measurement == "sensor_reading")
                |> filter(fn: (r) => r.sensor_id == "{sensor_id}")
                |> last()
            '''

            result = query_api.query(org=influxdb_manager.org, query=query)

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

    @staticmethod
    async def get_sensor_history(session: AsyncSession, sn: str, time_range: str, window: Optional[str] = None) -> dict:
        """动态智能聚合读取传感器时序历史数据，保留网络断连造成的空窗期"""
        ranges = {'1w': 7, '2w': 14, '1m': 30, '2m': 60, '3m': 90}
        days = ranges.get(time_range, 7)
        total_minutes = days * 24 * 60

        from pub.services.customer_service import HealthCheckFreqService
        freq = await HealthCheckFreqService.get_health_check_by_sensor_sn(session, sn)
        patrol_m = freq.patrol if freq else 60
        
        # 获取传感器的安装方向以供前端动态推断 XYZ 轴的真实物理含义
        direction_stmt = select(SensorMonitoring.direction).join(
            Sensor, Sensor.id == SensorMonitoring.sensor_id
        ).where(Sensor.sn == sn)
        direction_result = await session.execute(direction_stmt)
        direction = direction_result.scalar_one_or_none()

        # 计算实际的聚合粒度
        if window and window != 'auto':
            win_m = 60
            if window.endswith('h'):
                win_m = int(window[:-1]) * 60
            elif window.endswith('d'):
                win_m = int(window[:-1]) * 1440
            target_window_m = max(patrol_m, win_m) # 绝不能低于真实的采样频率
        else:
            # 智能适配最适宜的图表颗粒度：保证前端数据点数在合理的150个以内
            target_window_m = max(patrol_m, total_minutes // 150)

        # Flux 时间单位格式化
        if target_window_m >= 1440 and target_window_m % 1440 == 0:
            window_str = f"{target_window_m // 1440}d"
        elif target_window_m >= 60 and target_window_m % 60 == 0:
            window_str = f"{target_window_m // 60}h"
        else:
            window_str = f"{target_window_m}m"

        try:
            client = influxdb_manager.get_client()
            query_api = client.query_api()

            # Flux 查询: 提取基础数据后，不仅查 max，针对 rms_m 并发查询 min, first, last 凑齐 Candlestick 所需的 4 要素
            query = f'''
                data = from(bucket:"{influxdb_manager.bucket}")
                    |> range(start: -{days}d)
                    |> filter(fn: (r) => r.sn == "{sn}")
                    |> filter(fn: (r) => r._field == "temperature" or r._field == "rms_x" or r._field == "rms_y" or r._field == "rms_z" or r._field == "rms_m")
                
                data |> aggregateWindow(every: {window_str}, fn: max, createEmpty: true) |> yield(name: "max")
                data |> filter(fn: (r) => r._field == "rms_m" or r._field == "temperature") |> aggregateWindow(every: {window_str}, fn: min, createEmpty: true) |> yield(name: "min")
                data |> filter(fn: (r) => r._field == "rms_m" or r._field == "temperature") |> aggregateWindow(every: {window_str}, fn: first, createEmpty: true) |> yield(name: "first")
                data |> filter(fn: (r) => r._field == "rms_m" or r._field == "temperature") |> aggregateWindow(every: {window_str}, fn: last, createEmpty: true) |> yield(name: "last")
            '''

            result = await asyncio.to_thread(query_api.query, org=influxdb_manager.org, query=query)

            # 拼装数据对齐字典
            data_map = {}
            for table in result:
                yield_name = table.records[0].values.get("result") if table.records else None
                for record in table.records:
                    t = record.get_time().isoformat()
                    f = record.get_field()
                    v = record.get_value()
                    if t not in data_map:
                        data_map[t] = {
                            "temperature": None, "rms_x": None, "rms_y": None, "rms_z": None, "rms_m": None,
                            "rms_m_min": None, "rms_m_first": None, "rms_m_last": None,
                            "temp_min": None, "temp_first": None, "temp_last": None
                        }
                        
                    if yield_name == "max" and f in data_map[t]:
                        data_map[t][f] = v
                    elif yield_name == "min":
                        if f == "rms_m": data_map[t]["rms_m_min"] = v
                        elif f == "temperature": data_map[t]["temp_min"] = v
                    elif yield_name == "first":
                        if f == "rms_m": data_map[t]["rms_m_first"] = v
                        elif f == "temperature": data_map[t]["temp_first"] = v
                    elif yield_name == "last":
                        if f == "rms_m": data_map[t]["rms_m_last"] = v
                        elif f == "temperature": data_map[t]["temp_last"] = v

            sorted_times = sorted(data_map.keys())
            
            return {
                "meta": {
                    "patrol": patrol_m,
                    "window": window_str,
                    "points": len(sorted_times),
                    "direction": direction
                },
                "timestamps": sorted_times,
                "series": {
                    "temperature": [data_map[t]["temperature"] for t in sorted_times],
                    "temp_min": [data_map[t].get("temp_min") for t in sorted_times],
                    "temp_first": [data_map[t].get("temp_first") for t in sorted_times],
                    "temp_last": [data_map[t].get("temp_last") for t in sorted_times],
                    "rms_x": [data_map[t]["rms_x"] for t in sorted_times],
                    "rms_y": [data_map[t]["rms_y"] for t in sorted_times],
                    "rms_z": [data_map[t]["rms_z"] for t in sorted_times],
                    "rms_m": [data_map[t]["rms_m"] for t in sorted_times],
                    "rms_m_min": [data_map[t].get("rms_m_min") for t in sorted_times],
                    "rms_m_first": [data_map[t].get("rms_m_first") for t in sorted_times],
                    "rms_m_last": [data_map[t].get("rms_m_last") for t in sorted_times],
                }
            }
        except Exception as e:
            logger.error(f"Failed to get sensor history for SN {sn}: {e}")
            raise DomainException(code=500, message=f"时序数据库查询失败: {str(e)}")


class SensorConfigService:
    """Service for building device-side default_config.json from database."""

    @staticmethod
    async def get_config_by_sn(session: AsyncSession, sn: str) -> Optional[dict]:
        """Fetch the full device configuration for a given sensor SN.

        Returns a dict matching the structure of docs/default_config.json,
        or None if the sensor is not found / not linked to any monitoring record.
        """
        # 1. Find the Sensor and its active SensorMonitoring record
        stmt = (
            select(Sensor, SensorMonitoring, SensorBatch, SensorType)
            .outerjoin(SensorMonitoring, Sensor.id == SensorMonitoring.sensor_id)
            .outerjoin(SensorBatch, Sensor.sensor_batch_id == SensorBatch.id)
            .outerjoin(SensorType, SensorBatch.sensor_type_id == SensorType.id)
            .where(Sensor.sn == sn)
        )
        result = await session.execute(stmt)
        row = result.first()

        if not row:
            return None

        sensor, monitoring, batch, sensor_type = row

        # Defaults that mirror default_config.json
        config = {
            "iso": {"standard": 1, "category": 3, "foundation": 1},
            "rpm": 1480,
            "voltage": 19000,
            "host": "",
            "patrol": 60,
            "diagnosis": 1440,
            "report": 1,
            "network": 1,
            "wifi": {"ssid": "", "pass": ""},
            "configured": False,
        }

        # Early exit if no monitoring record or no device_inst
        if not monitoring or not monitoring.device_inst_id:
            return config

        # 2. Load device-side chain: DeviceInst → DeviceSpec → DeviceCategory
        stmt2 = (
            select(DeviceInst, DeviceSpec, DeviceCategory)
            .outerjoin(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .outerjoin(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(DeviceInst.id == monitoring.device_inst_id)
        )
        result2 = await session.execute(stmt2)
        device_row = result2.first()
        if not device_row:
            return config

        device_inst, device_spec, device_cat = device_row

        # 3. rpm from DeviceSpec
        if device_spec and device_spec.rpm is not None:
            config["rpm"] = device_spec.rpm

        if not device_cat:
            return config

        iso = None
        hcf = None
        tenant = None

        # 4. ISO standard
        if device_cat.iso_standard_id:
            iso = await session.get(IsoStandard, device_cat.iso_standard_id)
            if iso:
                config["iso"] = {
                    "standard": iso.version,
                    "category": iso.category,
                    "foundation": iso.foundation,
                }

        # 5. HealthCheckFreq (patrol, diagnosis, report)
        if device_cat.health_check_freq_id:
            hcf = await session.get(HealthCheckFreq, device_cat.health_check_freq_id)
            if hcf:
                config["patrol"] = hcf.patrol
                config["diagnosis"] = hcf.diagnosis
                config["report"] = hcf.report

        # 6. Tenant mqtt_server and api_server
        if device_cat.tenant_id:
            tenant = await session.get(Tenant, device_cat.tenant_id)
            if tenant:
                config["mqtt_host"] = tenant.mqtt_server or "mqtt.api-server.icu"
                config["api_host"] = tenant.api_server or "api.api-server.icu"

        # 7. SensorType values (battery, network)
        if sensor_type:
            config["voltage"] = sensor_type.battery
            config["network"] = sensor_type.network

        # 8. WiFi credentials via ProcessDeviceItem → ProcessDevice → Area
        stmt3 = (
            select(Area)
            .join(ProcessDevice, ProcessDevice.area_id == Area.id)
            .join(ProcessDeviceItem, ProcessDeviceItem.process_device_id == ProcessDevice.id)
            .where(ProcessDeviceItem.device_inst_id == device_inst.id)
            .limit(1)
        )
        result3 = await session.execute(stmt3)
        area = result3.scalar_one_or_none()
        if area:
            config["wifi"] = {
                "ssid": area.ssid or "",
                "pass": area.passwd or "",
            }

        # 9. configured = all critical links present
        config["configured"] = bool(
            iso and hcf and tenant and sensor_type
        )

        return config

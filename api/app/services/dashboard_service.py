"""
Dashboard service - business logic for dashboard aggregations
"""

import asyncio
import json
import logging
import copy
import time
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import redis_manager
from app.models.device import DeviceInst, DeviceSpec, DeviceCategory, Process, ProcessDevice, ProcessDeviceItem
from app.models.sensor import PatrolDiagnosticRecord, SensorMonitoring
from app.models.customer import Area, Tenant

logger = logging.getLogger(__name__)

# Redis key prefix for calendar daily cache
CALENDAR_DAILY_PREFIX = "calendar:daily:"
# Redis key for the full calendar cache (past 12 months)
CALENDAR_FULL_KEY = "calendar:full"
# TTL for cached historical data (7 days)
CALENDAR_CACHE_TTL = 604800

# Redis key prefix for device stats cache (no TTL, invalidated on data change)
DEVICE_STATS_PREFIX = "dashboard:device_stats:"


class DashboardService:
    """Service for handling dashboard data aggregations."""

    # ============================================================
    # Redis helpers
    # ============================================================

    @staticmethod
    def _get_redis_client():
        """Get Redis client safely."""
        try:
            return redis_manager.get_client()
        except RuntimeError:
            logger.warning("Redis not available for cache")
            return None

    # ============================================================
    # Device stats cache (permanent TTL, invalidated on data change)
    # ============================================================

    @staticmethod
    def _get_device_stats_cache_key(tenant_id: UUID) -> str:
        return f"{DEVICE_STATS_PREFIX}{tenant_id}"

    @staticmethod
    def invalidate_device_stats_cache(tenant_id: UUID) -> None:
        """清除设备统计缓存，由外部（路由层）在设备/分类/区域数据变更时调用"""
        client = DashboardService._get_redis_client()
        if not client:
            return
        try:
            key = DashboardService._get_device_stats_cache_key(tenant_id)
            client.delete(key)
            logger.info(f"Invalidated device stats cache for tenant {tenant_id}")
        except Exception as e:
            logger.error(f"Failed to invalidate device stats cache: {e}")

    @staticmethod
    async def rebuild_device_stats_cache_task(tenant_id: UUID) -> None:
        """后台任务：异步重建设备拓扑缓存。脱离原请求生命周期，由 BackgroundTasks 调用。"""
        from app.database import db_manager
        # 为后台任务独立获取新的数据库 Session
        async for session in db_manager.get_session():
            try:
                await DashboardService._get_topology_skeleton(session, tenant_id, force_rebuild=True)
                logger.info(f"Successfully rebuilt topology cache for tenant {tenant_id} in background")
                break
            except Exception as e:
                logger.error(f"Failed to rebuild topology cache in background for tenant {tenant_id}: {e}")

    @staticmethod
    async def _get_cached_device_stats(tenant_id: UUID) -> Optional[dict]:
        """从 Redis 读取缓存的设备基础统计数据"""
        client = DashboardService._get_redis_client()
        if not client:
            return None
        try:
            key = DashboardService._get_device_stats_cache_key(tenant_id)
            val = await asyncio.to_thread(client.get, key)
            if val is not None:
                return json.loads(val)
        except Exception as e:
            logger.debug(f"Failed to get cached device stats: {e}")
        return None

    @staticmethod
    async def _set_cached_device_stats(tenant_id: UUID, data: dict) -> None:
        """将设备基础统计数据写入 Redis 缓存（永久有效，无 TTL，由数据变更触发失效）"""
        client = DashboardService._get_redis_client()
        if not client:
            return
        try:
            key = DashboardService._get_device_stats_cache_key(tenant_id)
            await asyncio.to_thread(client.set, key, json.dumps(data))
            logger.info(f"Cached device stats for tenant {tenant_id}")
        except Exception as e:
            logger.error(f"Failed to cache device stats: {e}")

    # ============================================================
    # Overview
    # ============================================================

    @staticmethod
    async def _get_topology_skeleton(session: AsyncSession, tenant_id: UUID, force_rebuild: bool = False) -> dict:
        """获取并缓存静态拓扑骨架，将分类和区域树与设备关联关系分离"""
        if not force_rebuild:
            cached = await DashboardService._get_cached_device_stats(tenant_id)
            # 兼容处理：检查是否存在 deviceMeta 和 processMap，以防读取到遗留的旧版本缓存结构
            if cached and "deviceMeta" in cached and "processMap" in cached:
                return cached

        # 获取全量设备及其映射关系（无异常状态计算）
        stmt_dev = (
            select(
                DeviceInst.id,
                DeviceInst.code,
                DeviceInst.sn,
                DeviceInst.purchase_date,
                DeviceInst.active,
                DeviceCategory.id.label("category_id"),
                ProcessDevice.area_id.label("area_id"),
                ProcessDevice.process_id.label("process_id")
            )
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .outerjoin(ProcessDeviceItem, ProcessDeviceItem.device_inst_id == DeviceInst.id)
            .outerjoin(ProcessDevice, ProcessDevice.id == ProcessDeviceItem.process_device_id)
            .where(DeviceCategory.tenant_id == tenant_id)
        )
        dev_rows = await session.execute(stmt_dev)
        
        dev_map = {}
        for row in dev_rows:
            dev_id_str = str(row.id)
            if dev_id_str not in dev_map:
                dev_map[dev_id_str] = {
                    "active": row.active,
                    "code": row.code,
                    "sn": row.sn,
                    "purchase_date": row.purchase_date.isoformat() if row.purchase_date else None,
                    "category_id": str(row.category_id) if row.category_id else None,
                    "areas": set(),
                    "processes": set()
                }
            if row.area_id:
                dev_map[dev_id_str]["areas"].add(str(row.area_id))
            if row.process_id:
                dev_map[dev_id_str]["processes"].add(str(row.process_id))
                
        total_devices = len(dev_map)
        running_devices = sum(1 for info in dev_map.values() if info["active"] == 1)
        
        device_cat_map = {}
        device_area_map = {}
        device_process_map = {}
        device_meta = {}
        unassigned_devices = []
        
        for dev_id, info in dev_map.items():
            device_meta[dev_id] = {
                "code": info["code"], "sn": info["sn"], "purchase_date": info["purchase_date"]
            }
            if info["category_id"]:
                device_cat_map[dev_id] = info["category_id"]
            if info["areas"]:
                device_area_map[dev_id] = list(info["areas"])
            else:
                unassigned_devices.append(dev_id)
            if info["processes"]:
                device_process_map[dev_id] = list(info["processes"])

        # 获取分类骨架
        stmt_cats = select(DeviceCategory).where(DeviceCategory.tenant_id == tenant_id)
        cat_rows = (await session.execute(stmt_cats)).scalars().all()
        cat_map = {
            str(c.id): {
                "id": str(c.id),
                "name": c.name,
                "parent_id": str(c.parent_id) if c.parent_id else None,
                "total": 0,
                "anomaly": 0
            } for c in cat_rows
        }
        
        # 获取区域骨架
        stmt_areas = select(Area).where(Area.tenant_id == tenant_id)
        area_rows = (await session.execute(stmt_areas)).scalars().all()
        area_map = {
            str(a.id): {
                "id": str(a.id),
                "name": a.name,
                "parent_id": str(a.parent_id) if a.parent_id else None,
                "total": 0,
                "anomaly": 0
            } for a in area_rows
        }
        
        # 获取工段骨架
        stmt_processes = select(Process).where(Process.tenant_id == tenant_id)
        process_rows = (await session.execute(stmt_processes)).scalars().all()
        process_map = {
            str(p.id): {
                "id": str(p.id),
                "name": p.name,
                "parent_id": None,
                "total": 0,
                "anomaly": 0
            } for p in process_rows
        }
        
        # 静态骨架计算 - 分类 total 上卷
        for dev_id, cat_id in device_cat_map.items():
            curr = cat_id
            visited = set()
            while curr and curr in cat_map:
                if curr in visited: break
                visited.add(curr)
                cat_map[curr]["total"] += 1
                curr = cat_map[curr]["parent_id"]
                
        # 静态骨架计算 - 区域 total 上卷
        for dev_id, areas in device_area_map.items():
            for area_id in areas:
                curr = area_id
                visited = set()
                while curr and curr in area_map:
                    if curr in visited: break
                    visited.add(curr)
                    area_map[curr]["total"] += 1
                    curr = area_map[curr]["parent_id"]
                    
        # 静态骨架计算 - 工段 total
        for dev_id, processes in device_process_map.items():
            for process_id in processes:
                if process_id in process_map:
                    process_map[process_id]["total"] += 1
                    
        skeleton = {
            "totalDevices": total_devices,
            "runningDevices": running_devices,
            "catMap": cat_map,
            "deviceCatMap": device_cat_map,
            "areaMap": area_map,
            "deviceAreaMap": device_area_map,
            "processMap": process_map,
            "deviceProcessMap": device_process_map,
            "deviceMeta": device_meta,
            "unassignedTotal": len(unassigned_devices),
            "unassignedDevices": unassigned_devices
        }
        
        # 缓存永久保存，只有增删改数据时通过 invalidate 方法主动使其失效
        await DashboardService._set_cached_device_stats(tenant_id, skeleton)
        return skeleton

    @staticmethod
    async def get_overview(session: AsyncSession, tenant_id: UUID) -> dict:
        # 1. 尝试从 Redis 获取或重建静态拓扑骨架，并深拷贝防止内存污染
        skeleton = await DashboardService._get_topology_skeleton(session, tenant_id)
        skeleton = copy.deepcopy(skeleton)
        device_meta = skeleton["deviceMeta"]

        # 2. 今日新增 (利用缓存直接进行纯内存计算，0 次数据库查询)
        today_str = date.today().isoformat()
        new_devices_today = sum(1 for meta in device_meta.values() if meta.get("purchase_date") == today_str)

        # 3. 极速获取实时动态故障数据 (完全摒弃 JOIN，使用 IN 批量查询单表)
        dev_anomalies = {}
        recent_candidates = []
        device_ids = [UUID(dev_id) for dev_id in device_meta.keys()]
        
        if device_ids:
            # 分块查询防止 SQL 语句过长 (每 2000 个设备查一次)
            chunk_size = 2000
            for i in range(0, len(device_ids), chunk_size):
                chunk = device_ids[i:i + chunk_size]
                
                # 无 JOIN，直接查单表
                stmt_anomaly = (
                    select(SensorMonitoring.device_inst_id, SensorMonitoring.anomaly)
                    .where(
                        SensorMonitoring.device_inst_id.in_(chunk),
                        SensorMonitoring.anomaly > 0
                    )
                )
                for dev_id, anomaly in await session.execute(stmt_anomaly):
                    dev_id_str = str(dev_id)
                    if dev_id_str not in dev_anomalies:
                        dev_anomalies[dev_id_str] = set()
                    dev_anomalies[dev_id_str].add(anomaly)
                    
                # 最新预警，无 JOIN，查单表
                stmt_recent = (
                    select(
                        SensorMonitoring.id,
                        SensorMonitoring.device_inst_id,
                        SensorMonitoring.anomaly,
                        SensorMonitoring.ts
                    )
                    .where(
                        SensorMonitoring.device_inst_id.in_(chunk),
                        SensorMonitoring.anomaly > 0
                    )
                    .order_by(SensorMonitoring.ts.desc())
                    .limit(10)
                )
                recent_candidates.extend((await session.execute(stmt_recent)).all())
            
        faulty_devices = len(dev_anomalies)
        vibration_anomaly_count = sum(1 for a in dev_anomalies.values() if 1 in a)
        temperature_anomaly_count = sum(1 for a in dev_anomalies.values() if 2 in a)
        both_anomaly_count = sum(1 for a in dev_anomalies.values() if 3 in a)

        # 4. 内存染色：将动态故障数据极速注入到树状骨架中
        cat_map = skeleton["catMap"]
        area_map = skeleton["areaMap"]
        process_map = skeleton["processMap"]
        unassigned_anomaly = 0
        unassigned_set = set(skeleton["unassignedDevices"])
        
        for dev_id_str in dev_anomalies.keys():
            # 为分类树染色（计算故障数量并向上级累加）
            curr_cat = skeleton["deviceCatMap"].get(dev_id_str)
            visited = set()
            while curr_cat and curr_cat in cat_map:
                if curr_cat in visited: break
                visited.add(curr_cat)
                cat_map[curr_cat]["anomaly"] += 1
                curr_cat = cat_map[curr_cat]["parent_id"]
                
            # 为区域树染色
            curr_areas = skeleton["deviceAreaMap"].get(dev_id_str)
            if curr_areas:
                for curr_area in curr_areas:
                    visited_area = set()
                    while curr_area and curr_area in area_map:
                        if curr_area in visited_area: break
                        visited_area.add(curr_area)
                        area_map[curr_area]["anomaly"] += 1
                        curr_area = area_map[curr_area]["parent_id"]
            elif dev_id_str in unassigned_set:
                unassigned_anomaly += 1
                
            # 为工段染色
            curr_processes = skeleton["deviceProcessMap"].get(dev_id_str)
            if curr_processes:
                for curr_process in curr_processes:
                    if curr_process in process_map:
                        process_map[curr_process]["anomaly"] += 1

        # 将平行对象重组为前端所需的树状层级结构
        def assemble_tree(flat_map, root_name="全部", unassigned_total=0, unassigned_anom=0):
            for info in flat_map.values():
                info["children"] = []
                
            top_level = []
            for info in flat_map.values():
                pid = info["parent_id"]
                if pid and pid in flat_map:
                    flat_map[pid]["children"].append(info)
                else:
                    top_level.append(info)
                    
            if unassigned_total > 0:
                top_level.append({
                    "id": "__unassigned__",
                    "name": "未分配",
                    "parent_id": None,
                    "total": unassigned_total,
                    "anomaly": unassigned_anom,
                    "children": []
                })
                
            if top_level or unassigned_total > 0:
                return [{
                    "id": "__root__",
                    "name": root_name,
                    "parent_id": None,
                    "total": sum(c["total"] for c in top_level),
                    "anomaly": sum(c["anomaly"] for c in top_level),
                    "children": top_level
                }]
            return []
            
        devices_by_category_tree = assemble_tree(cat_map)
        devices_by_area_tree = assemble_tree(
            area_map, 
            unassigned_total=skeleton["unassignedTotal"], 
            unassigned_anom=unassigned_anomaly
        )
        devices_by_process_tree = assemble_tree(process_map)

        # 5. 内存组装最新预警所需信息 (由于砍掉了 JOIN，在内存里把 code 和 sn 拼装回来)
        recent_candidates.sort(key=lambda x: x.ts or 0, reverse=True)
        recent_anomalies = []
        for row in recent_candidates[:10]:
            dev_id_str = str(row.device_inst_id)
            meta = device_meta.get(dev_id_str, {})
            recent_anomalies.append({
                "id": str(row.id),
                "device_code": meta.get("code", "Unknown"),
                "device_sn": meta.get("sn", "Unknown"),
                "anomaly": row.anomaly,
                "ts": row.ts or 0
            })

        return {
            "totalDevices": skeleton["totalDevices"],
            "runningDevices": skeleton["runningDevices"],
            "faultyDevices": faulty_devices,
            "newDevicesToday": new_devices_today,
            "vibrationAnomalyCount": vibration_anomaly_count,
            "temperatureAnomalyCount": temperature_anomaly_count,
            "bothAnomalyCount": both_anomaly_count,
            "recentAnomalies": recent_anomalies,
            "devicesByCategoryTree": devices_by_category_tree,
            "devicesByAreaTree": devices_by_area_tree,
            "devicesByProcessTree": devices_by_process_tree,
        }

    @staticmethod
    def _get_level(count: int) -> int:
        """Convert fault device count to color level (0-5)."""
        if count <= 0:
            return 0
        elif count <= 2:
            return 1
        elif count <= 5:
            return 2
        elif count <= 10:
            return 3
        elif count <= 20:
            return 4
        else:
            return 5

    @staticmethod
    async def _query_daily_fault_count(session: AsyncSession, target_date: date) -> int:
        """Query the number of faulty devices for a specific date from PatrolDiagnosticRecord.
        
        Counts distinct SNs where health_status > 0 on the given date.
        Uses the `ts` field (Unix ms timestamp) for date filtering.
        """
        # Calculate start and end of the target date in Unix ms
        start_dt = datetime(target_date.year, target_date.month, target_date.day, tzinfo=None)
        end_dt = start_dt + timedelta(days=1)
        start_ts = int(start_dt.timestamp() * 1000)
        end_ts = int(end_dt.timestamp() * 1000)

        stmt = (
            select(func.count(func.distinct(PatrolDiagnosticRecord.sn)))
            .where(
                PatrolDiagnosticRecord.ts >= start_ts,
                PatrolDiagnosticRecord.ts < end_ts,
                PatrolDiagnosticRecord.health_status > 0,
            )
        )
        result = await session.execute(stmt)
        return result.scalar() or 0

    @staticmethod
    async def _get_cached_daily_count(date_str: str) -> Optional[int]:
        """Get cached daily fault count from Redis."""
        client = DashboardService._get_redis_client()
        if not client:
            return None
        try:
            key = f"{CALENDAR_DAILY_PREFIX}{date_str}"
            val = await asyncio.to_thread(client.get, key)
            if val is not None:
                return int(val)
        except Exception as e:
            logger.debug(f"Failed to get cached daily count for {date_str}: {e}")
        return None

    @staticmethod
    async def _set_cached_daily_count(date_str: str, count: int) -> None:
        """Cache daily fault count to Redis."""
        client = DashboardService._get_redis_client()
        if not client:
            return
        try:
            key = f"{CALENDAR_DAILY_PREFIX}{date_str}"
            await asyncio.to_thread(client.setex, key, CALENDAR_CACHE_TTL, count)
        except Exception as e:
            logger.debug(f"Failed to cache daily count for {date_str}: {e}")

    @staticmethod
    async def get_calendar_data(session: AsyncSession, tenant_id: UUID) -> dict:
        """Get calendar heatmap data for the past 12 months (including current month).
        
        Returns exactly 12 months: from 11 months ago to current month.
        e.g., if today is 2026-05-25, returns months 2025-06 through 2026-05.
        
        Also returns the tenant's create_at date to distinguish pre-creation vs
        post-creation dates in the frontend heatmap.
        
        Performance: Uses a single batch query for all dates, then fills in
        per-day counts from the result set. Redis cache is used for historical
        data to avoid repeated DB queries across requests.
        """
        today = date.today()
        
        # Query tenant's start_at (fixed, never changes)
        stmt_tenant = select(Tenant.start_at).where(Tenant.id == tenant_id)
        tenant_start_at = (await session.execute(stmt_tenant)).scalar()
        start_at_str = tenant_start_at.isoformat() if tenant_start_at else today.isoformat()
        
        # Calculate the date range: 12 months ago to today
        start_date = date(today.year, today.month, 1)
        # Go back 11 months to get the first day of the range
        for _ in range(11):
            if start_date.month > 1:
                start_date = date(start_date.year, start_date.month - 1, 1)
            else:
                start_date = date(start_date.year - 1, 12, 1)
        
        # Try to get full calendar data from Redis cache (excluding today)
        cached_data = await DashboardService._get_cached_full_calendar(start_date, today)
        
        if cached_data:
            # Only need to query today's data
            today_str = today.isoformat()
            today_count = await DashboardService._query_daily_fault_count(session, today)
            today_level = DashboardService._get_level(today_count)
            
            # Update today's data in the cached result
            for month in cached_data["months"]:
                for day in month["days"]:
                    if day["date"] == today_str:
                        day["count"] = today_count
                        day["level"] = today_level
                        break
            
            cached_data["start_at"] = start_at_str
            return cached_data
        
        # Cache miss: batch query all dates from database
        # Calculate start and end timestamps (Unix ms)
        start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=None)
        end_dt = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=None)
        start_ts = int(start_dt.timestamp() * 1000)
        end_ts = int(end_dt.timestamp() * 1000)
        
        # Single batch query: group by date and count distinct SNs per day
        # Use ts field to extract date (divide by 86400000 ms per day)
        stmt = (
            select(
                func.floor(PatrolDiagnosticRecord.ts / 86400000).label("day_offset"),
                func.count(func.distinct(PatrolDiagnosticRecord.sn)).label("cnt"),
            )
            .where(
                PatrolDiagnosticRecord.ts >= start_ts,
                PatrolDiagnosticRecord.ts < end_ts,
                PatrolDiagnosticRecord.health_status > 0,
            )
            .group_by(func.floor(PatrolDiagnosticRecord.ts / 86400000))
        )
        result = await session.execute(stmt)
        
        # Build lookup: date_str -> count
        # day_offset is days since epoch (1970-01-01)
        epoch = date(1970, 1, 1)
        daily_counts: dict[str, int] = {}
        for row in result.all():
            day_date = epoch + timedelta(days=int(row.day_offset))
            daily_counts[day_date.isoformat()] = row.cnt
        
        # Build month-by-month response
        months_data = []
        current = start_date
        while current <= today:
            month = current.month
            year = current.year
            
            # Last day of this month
            if month == 12:
                next_month = date(year + 1, 1, 1)
            else:
                next_month = date(year, month + 1, 1)
            last_day = next_month - timedelta(days=1)
            
            days_in_month = []
            day = current
            while day <= last_day and day <= today:
                date_str = day.isoformat()
                count = daily_counts.get(date_str, 0)
                level = DashboardService._get_level(count)
                days_in_month.append({
                    "date": date_str,
                    "count": count,
                    "level": level,
                })
                day += timedelta(days=1)
            
            months_data.append({
                "month": month,
                "days": days_in_month,
            })
            
            current = next_month
        
        result_data = {
            "year": today.year,
            "months": months_data,
            "start_at": start_at_str,
        }
        
        # Cache the full result (excluding today's data which is always fresh)
        await DashboardService._set_cached_full_calendar(result_data, today)
        
        return result_data

    @staticmethod
    def _get_cached_full_calendar_key(start_date: date, today: date) -> str:
        """Generate cache key for full calendar data."""
        return f"{CALENDAR_FULL_KEY}:{start_date.isoformat()}:{today.isoformat()}"

    @staticmethod
    async def _get_cached_full_calendar(start_date: date, today: date) -> Optional[dict]:
        """Get full calendar data from Redis cache (excluding today)."""
        client = DashboardService._get_redis_client()
        if not client:
            return None
        try:
            key = DashboardService._get_cached_full_calendar_key(start_date, today)
            val = await asyncio.to_thread(client.get, key)
            if val is not None:
                return json.loads(val)
        except Exception as e:
            logger.debug(f"Failed to get cached full calendar: {e}")
        return None

    @staticmethod
    async def _set_cached_full_calendar(data: dict, today: date) -> None:
        """Cache full calendar data to Redis (with today's count set to 0 for caching)."""
        client = DashboardService._get_redis_client()
        if not client:
            return
        try:
            # Set today's count to 0 for caching (will be queried fresh each time)
            today_str = today.isoformat()
            for month in data["months"]:
                for day in month["days"]:
                    if day["date"] == today_str:
                        day["count"] = 0
                        day["level"] = 0
                        break
            
            key = DashboardService._get_cached_full_calendar_key(
                date.fromisoformat(data["months"][0]["days"][0]["date"]),
                today
            )
            await asyncio.to_thread(client.setex, key, CALENDAR_CACHE_TTL, json.dumps(data))
        except Exception as e:
            logger.debug(f"Failed to cache full calendar: {e}")

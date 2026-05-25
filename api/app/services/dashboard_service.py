"""
Dashboard service - business logic for dashboard aggregations
"""

import json
import logging
import time
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import redis_manager
from app.models.device import DeviceInst, DeviceSpec, DeviceCategory, ProcessDevice, ProcessDeviceItem
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
    def _get_cached_device_stats(tenant_id: UUID) -> Optional[dict]:
        """从 Redis 读取缓存的设备基础统计数据"""
        client = DashboardService._get_redis_client()
        if not client:
            return None
        try:
            key = DashboardService._get_device_stats_cache_key(tenant_id)
            val = client.get(key)
            if val is not None:
                return json.loads(val)
        except Exception as e:
            logger.debug(f"Failed to get cached device stats: {e}")
        return None

    @staticmethod
    def _set_cached_device_stats(tenant_id: UUID, data: dict) -> None:
        """将设备基础统计数据写入 Redis 缓存（永久有效，无 TTL，由数据变更触发失效）"""
        client = DashboardService._get_redis_client()
        if not client:
            return
        try:
            key = DashboardService._get_device_stats_cache_key(tenant_id)
            client.set(key, json.dumps(data))
            logger.info(f"Cached device stats for tenant {tenant_id}")
        except Exception as e:
            logger.error(f"Failed to cache device stats: {e}")

    # ============================================================
    # Overview
    # ============================================================

    @staticmethod
    async def get_overview(session: AsyncSession, tenant_id: UUID) -> dict:
        # 1. 先尝试从 Redis 读取缓存的设备基础数据
        cached = DashboardService._get_cached_device_stats(tenant_id)

        if cached:
            total_devices = cached["totalDevices"]
            running_devices = cached["runningDevices"]
            devices_by_category_tree = cached["devicesByCategoryTree"]
            devices_by_area_tree = cached["devicesByAreaTree"]
        else:
            # 缓存未命中，查询 DB
            # 1a. 设备总数
            stmt_total = (
                select(func.count(DeviceInst.id))
                .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
                .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
                .where(DeviceCategory.tenant_id == tenant_id)
            )
            total_devices = (await session.execute(stmt_total)).scalar() or 0

            # 1b. 运行设备 (active == 1)
            stmt_running = stmt_total.where(DeviceInst.active == 1)
            running_devices = (await session.execute(stmt_running)).scalar() or 0

            # 1c. 按设备分类树聚合设备总数和异常设备数
            devices_by_category_tree = await DashboardService._get_category_device_tree(
                session, tenant_id
            )

            # 1d. 按区域树聚合设备总数和异常设备数
            devices_by_area_tree = await DashboardService._get_area_device_tree(
                session, tenant_id
            )

            # 写入缓存
            DashboardService._set_cached_device_stats(tenant_id, {
                "totalDevices": total_devices,
                "runningDevices": running_devices,
                "devicesByCategoryTree": devices_by_category_tree,
                "devicesByAreaTree": devices_by_area_tree,
            })

        # 2. 今日新增 (取 purchase_date 等于今天的数量) — 实时查询
        stmt_total_base = (
            select(func.count(DeviceInst.id))
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(DeviceCategory.tenant_id == tenant_id)
        )
        stmt_new = stmt_total_base.where(DeviceInst.purchase_date == date.today())
        new_devices_today = (await session.execute(stmt_new)).scalar() or 0

        # 3. 故障设备数 (对应有关联传感器且 anomaly > 0 的不重复设备数) — 实时查询
        stmt_faulty = (
            select(func.count(func.distinct(SensorMonitoring.device_inst_id)))
            .join(DeviceInst, SensorMonitoring.device_inst_id == DeviceInst.id)
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(
                DeviceCategory.tenant_id == tenant_id,
                SensorMonitoring.anomaly > 0
            )
        )
        faulty_devices = (await session.execute(stmt_faulty)).scalar() or 0

        # 3a. 按异常类型分类统计 (anomaly=1 震动异常, anomaly=2 温度异常, anomaly=3 双异常)
        async def _count_by_anomaly(anomaly_value: int) -> int:
            stmt = (
                select(func.count(func.distinct(SensorMonitoring.device_inst_id)))
                .join(DeviceInst, SensorMonitoring.device_inst_id == DeviceInst.id)
                .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
                .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
                .where(
                    DeviceCategory.tenant_id == tenant_id,
                    SensorMonitoring.anomaly == anomaly_value
                )
            )
            return (await session.execute(stmt)).scalar() or 0

        vibration_anomaly_count = await _count_by_anomaly(1)
        temperature_anomaly_count = await _count_by_anomaly(2)
        both_anomaly_count = await _count_by_anomaly(3)

        # 4. 最新故障预警 (获取存在异常的设备及相关信息，按时间倒序) — 实时查询
        stmt_recent = (
            select(
                SensorMonitoring.id,
                DeviceInst.code.label("device_code"),
                DeviceInst.sn.label("device_sn"),
                SensorMonitoring.anomaly,
                SensorMonitoring.ts
            )
            .join(DeviceInst, SensorMonitoring.device_inst_id == DeviceInst.id)
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(
                DeviceCategory.tenant_id == tenant_id,
                SensorMonitoring.anomaly > 0
            )
            .order_by(SensorMonitoring.ts.desc())
            .limit(10)
        )
        recent_result = await session.execute(stmt_recent)
        recent_anomalies = [
            {
                "id": str(row.id),
                "device_code": row.device_code,
                "device_sn": row.device_sn,
                "anomaly": row.anomaly,
                "ts": row.ts or 0
            } for row in recent_result.all()
        ]

        return {
            "totalDevices": total_devices,
            "runningDevices": running_devices,
            "faultyDevices": faulty_devices,
            "newDevicesToday": new_devices_today,
            "vibrationAnomalyCount": vibration_anomaly_count,
            "temperatureAnomalyCount": temperature_anomaly_count,
            "bothAnomalyCount": both_anomaly_count,
            "recentAnomalies": recent_anomalies,
            "devicesByCategoryTree": devices_by_category_tree,
            "devicesByAreaTree": devices_by_area_tree,
        }

    @staticmethod
    async def _get_category_device_tree(
        session: AsyncSession, tenant_id: UUID
    ) -> list:
        """
        按设备分类树聚合设备总数和异常设备数。
        先确定分类树结构，再统计每个分类下的设备总数和异常设备数。
        返回树形结构: [{name, total, anomaly, children: [...]}]
        """
        # 1. 获取该租户下所有 DeviceCategory
        stmt_cats = (
            select(DeviceCategory)
            .where(DeviceCategory.tenant_id == tenant_id)
        )
        cat_rows = (await session.execute(stmt_cats)).scalars().all()

        # 构建分类字典，包含基础统计字段 (统一转为 str 确保查找匹配)
        cat_map = {}
        for cat in cat_rows:
            cat_map[str(cat.id)] = {
                "id": str(cat.id),
                "name": cat.name,
                "parent_id": str(cat.parent_id) if cat.parent_id else None,
                "total": 0,
                "anomaly": 0,
                "children": [],
            }

        # 2. 完全按建议算法：将设备实例、规格、分类、异常测点提取合并为一个平铺组合数据
        stmt_devices = (
            select(
                DeviceInst.id.label("inst_id"),
                DeviceInst.code.label("instance_name"),
                DeviceSpec.id.label("spec_id"),
                DeviceCategory.id.label("category_id"),
                func.max(SensorMonitoring.anomaly).label("anomaly")
            )
            .select_from(DeviceInst)
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .outerjoin(SensorMonitoring, SensorMonitoring.device_inst_id == DeviceInst.id)
            .where(DeviceCategory.tenant_id == tenant_id)
            .group_by(DeviceInst.id, DeviceInst.code, DeviceSpec.id, DeviceCategory.id)
        )
        device_rows = (await session.execute(stmt_devices)).all()

        # 3. 对组合数据进行在内存中的精确累加 (从叶子向所有祖级传递)
        for row in device_rows:
            cid = str(row.category_id) if row.category_id else None
            if not cid or cid not in cat_map:
                continue
                
            is_anomaly = 1 if (row.anomaly and row.anomaly > 0) else 0
            
            # 将当前实例的数据累加到自身直接分类，并不断向上追溯累加到全部上级父分类
            curr_cid = cid
            visited = set()
            while curr_cid and curr_cid in cat_map:
                if curr_cid in visited:
                    break  # 防止数据中的死循环环状关联
                visited.add(curr_cid)
                
                cat_map[curr_cid]["total"] += 1
                cat_map[curr_cid]["anomaly"] += is_anomaly
                
                curr_cid = cat_map[curr_cid]["parent_id"]

        # 4. 组装父子树形结构提供给前端
        top_level_cats = []
        for cid, info in cat_map.items():
            pid = info["parent_id"]
            if pid and pid in cat_map:
                cat_map[pid]["children"].append(info)
            else:
                # 无父节点的即为最顶层根节点
                top_level_cats.append(info)

        # 5. 始终创建一个"全部"根节点，包裹所有顶层分类
        if len(top_level_cats) > 0:
            tree = [{
                "id": "__root__",
                "name": "全部",
                "parent_id": None,
                "total": sum(c["total"] for c in top_level_cats),
                "anomaly": sum(c["anomaly"] for c in top_level_cats),
                "children": top_level_cats,
            }]
        else:
            tree = []

        print("=== NestedPieChart Tree Data ===")
        print(json.dumps(tree, ensure_ascii=False, indent=2))

        return tree


    @staticmethod
    async def _get_area_device_tree(
        session: AsyncSession, tenant_id: UUID
    ) -> list:
        """
        按区域树聚合设备总数和异常设备数。
        关联路径: DeviceInst → ProcessDeviceItem → ProcessDevice → Area
        返回树形结构: [{name, total, anomaly, children: [...]}]
        """
        # 1. 获取该租户下所有 Area
        stmt_areas = (
            select(Area)
            .where(Area.tenant_id == tenant_id)
        )
        area_rows = (await session.execute(stmt_areas)).scalars().all()

        # 构建区域字典
        area_map = {}
        for area in area_rows:
            area_map[str(area.id)] = {
                "id": str(area.id),
                "name": area.name,
                "parent_id": str(area.parent_id) if area.parent_id else None,
                "total": 0,
                "anomaly": 0,
                "children": [],
            }

        # 2. 查询设备实例 → ProcessDeviceItem → ProcessDevice → Area 的关联
        #    同时 LEFT JOIN SensorMonitoring 获取异常信息
        #    使用 LEFT JOIN 确保即使设备未关联 ProcessDevice 也能被统计到"未分配区域"
        stmt_devices = (
            select(
                DeviceInst.id.label("inst_id"),
                DeviceInst.code.label("instance_name"),
                ProcessDevice.area_id.label("area_id"),
                func.max(SensorMonitoring.anomaly).label("anomaly"),
            )
            .select_from(DeviceInst)
            .outerjoin(ProcessDeviceItem, ProcessDeviceItem.device_inst_id == DeviceInst.id)
            .outerjoin(ProcessDevice, ProcessDevice.id == ProcessDeviceItem.process_device_id)
            .outerjoin(SensorMonitoring, SensorMonitoring.device_inst_id == DeviceInst.id)
            .group_by(DeviceInst.id, DeviceInst.code, ProcessDevice.area_id)
        )
        device_rows = (await session.execute(stmt_devices)).all()

        # 3. 对组合数据进行在内存中的精确累加 (从叶子向所有祖级传递)
        #    先统计"未分配区域"的设备
        unassigned_total = 0
        unassigned_anomaly = 0

        for row in device_rows:
            aid = str(row.area_id) if row.area_id else None
            if not aid or aid not in area_map:
                # 设备未关联到任何已知区域，归入"未分配区域"
                is_anomaly = 1 if (row.anomaly and row.anomaly > 0) else 0
                unassigned_total += 1
                unassigned_anomaly += is_anomaly
                continue

            is_anomaly = 1 if (row.anomaly and row.anomaly > 0) else 0

            # 将当前实例的数据累加到自身直接区域，并不断向上追溯累加到全部上级父区域
            curr_aid = aid
            visited = set()
            while curr_aid and curr_aid in area_map:
                if curr_aid in visited:
                    break  # 防止数据中的死循环环状关联
                visited.add(curr_aid)

                area_map[curr_aid]["total"] += 1
                area_map[curr_aid]["anomaly"] += is_anomaly

                curr_aid = area_map[curr_aid]["parent_id"]

        # 如果有未分配区域的设备，添加一个虚拟根节点包裹所有区域和未分配设备
        if unassigned_total > 0 or len(area_map) > 0:
            # 先组装父子关系：将子区域挂载到父区域的 children 中
            for aid, info in area_map.items():
                pid = info["parent_id"]
                if pid and pid in area_map:
                    area_map[pid]["children"].append(info)

            # 提取所有顶层区域（没有父节点或父节点不在 area_map 中的）
            top_level_areas = []
            for aid, info in area_map.items():
                if not info["parent_id"] or info["parent_id"] not in area_map:
                    top_level_areas.append(info)

            # 如果存在未分配设备，添加"未分配区域"节点
            if unassigned_total > 0:
                top_level_areas.append({
                    "id": "__unassigned__",
                    "name": "未分配",
                    "parent_id": None,
                    "total": unassigned_total,
                    "anomaly": unassigned_anomaly,
                    "children": [],
                })


            # 始终创建一个"全部"根节点，包裹所有顶层区域和未分配区域
            tree = [{
                "id": "__root__",
                "name": "全部",
                "parent_id": None,
                "total": sum(a["total"] for a in top_level_areas),
                "anomaly": sum(a["anomaly"] for a in top_level_areas),
                "children": top_level_areas,
            }]

        else:
            tree = []

        print("=== Area Tree Data ===")
        print(json.dumps(tree, ensure_ascii=False, indent=2))

        return tree

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
            val = client.get(key)
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
            client.setex(key, CALENDAR_CACHE_TTL, count)
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
            val = client.get(key)
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
            client.setex(key, CALENDAR_CACHE_TTL, json.dumps(data))
        except Exception as e:
            logger.debug(f"Failed to cache full calendar: {e}")

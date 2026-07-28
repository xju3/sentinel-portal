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

from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from pub.manager.database import redis_manager
from pub.models.device import (
    DeviceInst,
    DeviceSpec,
    DeviceCategory,
    Process,
    ProcessDevice,
    ProcessDeviceItem,
)
from pub.models.diagnosis import Diagnosis, DiagnosisItem
from pub.models.sensor import (
    PatrolDiagnosticRecord,
    Sensor,
    CommunicationState,
    SensorMonitoring,
)
from pub.models.customer import Area, Tenant

logger = logging.getLogger(__name__)

# Redis key prefix for calendar daily cache
CALENDAR_DAILY_PREFIX = "dashboard:calendar:v1:daily:"
# Redis key for the full calendar cache (past 12 months)
CALENDAR_FULL_KEY = "dashboard:calendar:v1:full"
# TTL for cached historical data (7 days)
CALENDAR_CACHE_TTL = 604800

# Redis key prefix for device stats cache (no TTL, invalidated on data change)
DEVICE_STATS_PREFIX = "dashboard:device_stats:"

INT_TO_LEVEL = {
    0: "正常",
    1: "关注",
    2: "异常",
    3: "警告",
    4: "严重",
}

DIAGNOSIS_LEVEL_SCORE = {
    "未检测": -1,
    "正常": 0,
    "关注": 1,
    "异常": 2,
    "警告": 3,
    "严重": 4,
}

DASHBOARD_METRIC_LABELS = {
    0: "温度",
    1: "振动(X轴)",
    2: "振动(Y轴)",
    3: "振动(Z轴)",
}

OFFLINE_AFTER_MS = 24 * 60 * 60 * 1000
SLOW_DURATION_MS = 60 * 1000


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
    async def _query_daily_fault_count(session: AsyncSession, tenant_id: UUID, target_date: date) -> int:
        """Query the number of faulty devices for a specific date from Diagnosis.

        Counts distinct device_ids where overall_level > 0 on the given date.
        """
        # Calculate start and end of the target date
        start_dt = datetime(
            target_date.year, target_date.month, target_date.day, tzinfo=None
        )
        end_dt = start_dt + timedelta(days=1)

        stmt = (
            select(func.count(func.distinct(Diagnosis.device_id)))
            .join(DeviceInst, DeviceInst.id == Diagnosis.device_id)
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(
                DeviceCategory.tenant_id == tenant_id,
                Diagnosis.diagnosed_at >= start_dt,
                Diagnosis.diagnosed_at < end_dt,
                Diagnosis.overall_level > 0,
                Diagnosis.resampling == 0,
            )
        )
        result = await session.execute(stmt)
        return result.scalar() or 0

    @staticmethod
    async def _get_cached_daily_count(tenant_id: UUID, date_str: str) -> Optional[int]:
        """Get cached daily fault count from Redis."""
        client = DashboardService._get_redis_client()
        if not client:
            return None
        try:
            key = f"{CALENDAR_DAILY_PREFIX}{tenant_id}:{date_str}"
            val = await asyncio.to_thread(client.get, key)
            if val is not None:
                return int(val)
        except Exception as e:
            logger.debug(f"Failed to get cached daily count for {date_str}: {e}")
        return None

    @staticmethod
    async def _set_cached_daily_count(
        tenant_id: UUID, date_str: str, count: int
    ) -> None:
        """Cache daily fault count to Redis."""
        client = DashboardService._get_redis_client()
        if not client:
            return
        try:
            key = f"{CALENDAR_DAILY_PREFIX}{tenant_id}:{date_str}"
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
        start_at_str = (
            tenant_start_at.isoformat() if tenant_start_at else today.isoformat()
        )

        # Calculate the date range: 12 months ago to today
        start_date = date(today.year, today.month, 1)
        # Go back 11 months to get the first day of the range
        for _ in range(11):
            if start_date.month > 1:
                start_date = date(start_date.year, start_date.month - 1, 1)
            else:
                start_date = date(start_date.year - 1, 12, 1)

        # Try to get full calendar data from Redis cache (excluding today)
        cached_data = await DashboardService._get_cached_full_calendar(
            tenant_id, start_date, today
        )

        if cached_data:
            # Only need to query today's data
            today_str = today.isoformat()
            today_count = await DashboardService._query_daily_fault_count(
                session, tenant_id, today
            )
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
        start_dt = datetime(
            start_date.year, start_date.month, start_date.day, tzinfo=None
        )
        end_dt = datetime(today.year, today.month, today.day, tzinfo=None) + timedelta(days=1)

        # Single batch query: group by date and count distinct device_ids per day
        stmt = (
            select(
                func.date(Diagnosis.diagnosed_at).label("day_date"),
                func.count(func.distinct(Diagnosis.device_id)).label("cnt"),
            )
            .join(DeviceInst, DeviceInst.id == Diagnosis.device_id)
            .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(
                DeviceCategory.tenant_id == tenant_id,
                Diagnosis.diagnosed_at >= start_dt,
                Diagnosis.diagnosed_at < end_dt,
                Diagnosis.overall_level > 0,
                Diagnosis.resampling == 0,
            )
            .group_by(func.date(Diagnosis.diagnosed_at))
        )
        result = await session.execute(stmt)

        # Build lookup: date_str -> count
        daily_counts: dict[str, int] = {}
        for row in result.all():
            if row.day_date:
                # row.day_date could be a datetime.date object or a string depending on dialect
                if isinstance(row.day_date, str):
                    daily_counts[row.day_date] = row.cnt
                else:
                    daily_counts[row.day_date.isoformat()] = row.cnt

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
                days_in_month.append(
                    {
                        "date": date_str,
                        "count": count,
                        "level": level,
                    }
                )
                day += timedelta(days=1)

            months_data.append(
                {
                    "month": month,
                    "days": days_in_month,
                }
            )

            current = next_month

        result_data = {
            "year": today.year,
            "months": months_data,
            "start_at": start_at_str,
        }

        # Cache the full result (excluding today's data which is always fresh)
        await DashboardService._set_cached_full_calendar(
            tenant_id, result_data, today
        )

        return result_data

    @staticmethod
    def _get_cached_full_calendar_key(
        tenant_id: UUID, start_date: date, today: date
    ) -> str:
        """Generate cache key for full calendar data."""
        return (
            f"{CALENDAR_FULL_KEY}:{tenant_id}:"
            f"{start_date.isoformat()}:{today.isoformat()}"
        )

    @staticmethod
    async def _get_cached_full_calendar(
        tenant_id: UUID, start_date: date, today: date
    ) -> Optional[dict]:
        """Get full calendar data from Redis cache (excluding today)."""
        client = DashboardService._get_redis_client()
        if not client:
            return None
        try:
            key = DashboardService._get_cached_full_calendar_key(
                tenant_id, start_date, today
            )
            val = await asyncio.to_thread(client.get, key)
            if val is not None:
                return json.loads(val)
        except Exception as e:
            logger.debug(f"Failed to get cached full calendar: {e}")
        return None

    @staticmethod
    async def _set_cached_full_calendar(
        tenant_id: UUID, data: dict, today: date
    ) -> None:
        """Cache full calendar data to Redis (with today's count set to 0 for caching)."""
        client = DashboardService._get_redis_client()
        if not client:
            return
        try:
            cached_data = copy.deepcopy(data)
            # Set today's count to 0 only in the cached copy. The first response
            # must keep the real count returned by the database query.
            today_str = today.isoformat()
            for month in cached_data["months"]:
                for day in month["days"]:
                    if day["date"] == today_str:
                        day["count"] = 0
                        day["level"] = 0
                        break

            key = DashboardService._get_cached_full_calendar_key(
                tenant_id,
                date.fromisoformat(cached_data["months"][0]["days"][0]["date"]),
                today,
            )
            await asyncio.to_thread(
                client.setex,
                key,
                CALENDAR_CACHE_TTL,
                json.dumps(cached_data),
            )
        except Exception as e:
            logger.debug(f"Failed to cache full calendar: {e}")

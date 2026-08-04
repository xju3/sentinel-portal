"""Historical temperature and vibration trends for one monitoring point."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pub.manager.database import influxdb_manager, redis_manager
from pub.models.customer import HealthCheckFreq
from pub.models.device import DeviceCategory, DeviceInst, DeviceSpec
from pub.utils.redis_keys import REDIS_KEY_DEVICE_POINT_TREND


logger = logging.getLogger(__name__)


class DevicePointTrendService:
    """Read point-scoped raw or downsampled trend data from InfluxDB."""

    RANGE_DAYS = {3, 7, 14, 30, 90, 180, 365}
    DEFAULT_WINDOWS = {
        3: 0,
        7: 60,
        14: 120,
        30: 240,
        90: 720,
        180: 1440,
        365: 1440,
    }
    ALLOWED_WINDOWS = {0, 60, 120, 240, 480, 720, 1440}
    CACHE_SECONDS = 60

    @classmethod
    def normalize_options(
        cls,
        range_days: int,
        window_minutes: int | None,
        patrol_minutes: float,
    ) -> tuple[int, int]:
        if range_days not in cls.RANGE_DAYS:
            raise ValueError("unsupported trend range")

        requested_window = (
            cls.DEFAULT_WINDOWS[range_days]
            if window_minutes is None
            else window_minutes
        )
        if requested_window not in cls.ALLOWED_WINDOWS:
            raise ValueError("unsupported trend window")

        # Raw data is intentionally available only for the default three-day view.
        # Longer raw queries can become unbounded during high-frequency testing.
        if requested_window == 0 and range_days != 3:
            raise ValueError("raw data is available only for the three-day range")

        if requested_window == 0:
            return range_days, 0
        return range_days, max(requested_window, max(1, math.ceil(patrol_minutes)))

    @staticmethod
    async def get_patrol_minutes(
        session: AsyncSession,
        device_id: UUID,
    ) -> float:
        statement = (
            select(HealthCheckFreq.patrol)
            .join(
                DeviceCategory,
                DeviceCategory.health_check_freq_id == HealthCheckFreq.id,
            )
            .join(
                DeviceSpec,
                DeviceSpec.device_category_id == DeviceCategory.id,
            )
            .join(DeviceInst, DeviceInst.device_spec_id == DeviceSpec.id)
            .where(DeviceInst.id == device_id)
        )
        value = (await session.execute(statement)).scalar_one_or_none()
        return float(value) if value is not None else 60.0

    @classmethod
    async def get_trends(
        cls,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        device_id: UUID,
        location_id: UUID,
        range_days: int,
        window_minutes: int | None = None,
    ) -> dict[str, Any]:
        patrol_minutes = await cls.get_patrol_minutes(session, device_id)
        range_days, effective_window = cls.normalize_options(
            range_days,
            window_minutes,
            patrol_minutes,
        )
        cache_key = REDIS_KEY_DEVICE_POINT_TREND.format(
            tenant_id=tenant_id,
            device_id=device_id,
            location_id=location_id,
            range_days=range_days,
            window_minutes=effective_window,
        )
        cached = cls._read_cache(cache_key)
        if cached is not None:
            return cached

        end_at = datetime.now(timezone.utc)
        start_at = end_at - timedelta(days=range_days)
        result = await cls._query_influx(
            device_id=device_id,
            location_id=location_id,
            start_at=start_at,
            end_at=end_at,
            window_minutes=effective_window,
        )
        result["meta"] = {
            "rangeDays": range_days,
            "windowMinutes": effective_window,
            "raw": effective_window == 0,
            "patrolMinutes": patrol_minutes,
            "startAt": start_at.isoformat().replace("+00:00", "Z"),
            "endAt": end_at.isoformat().replace("+00:00", "Z"),
            "pointCount": len(result["timestamps"]),
        }
        cls._write_cache(cache_key, result)
        return result

    @classmethod
    async def _query_influx(
        cls,
        *,
        device_id: UUID,
        location_id: UUID,
        start_at: datetime,
        end_at: datetime,
        window_minutes: int,
    ) -> dict[str, Any]:
        client = influxdb_manager.get_client()
        query_api = client.query_api()
        query = cls.build_flux_query(
            bucket=influxdb_manager.bucket,
            device_id=device_id,
            location_id=location_id,
            start_at=start_at,
            end_at=end_at,
            window_minutes=window_minutes,
        )
        tables = await asyncio.to_thread(
            query_api.query,
            org=influxdb_manager.org,
            query=query,
        )
        return cls.parse_records(tables, aggregated=window_minutes > 0)

    @staticmethod
    def build_flux_query(
        *,
        bucket: str,
        device_id: UUID,
        location_id: UUID,
        start_at: datetime,
        end_at: datetime,
        window_minutes: int,
    ) -> str:
        start = start_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        end = end_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        base = f'''from(bucket: "{bucket}")
  |> range(start: time(v: "{start}"), stop: time(v: "{end}"))
  |> filter(fn: (r) => r._measurement == "vibration_feature")
  |> filter(fn: (r) => r.device_id == "{device_id}")
  |> filter(fn: (r) => r.location_id == "{location_id}")
  |> filter(fn: (r) => r._field == "temperature" or r._field == "max_rms_vel")
  |> group(columns: ["_field"])'''
        if window_minutes == 0:
            return f"{base}\n  |> sort(columns: [\"_time\"])"

        return f'''data = {base}

data |> aggregateWindow(every: {window_minutes}m, fn: mean, createEmpty: true) |> yield(name: "mean")
data |> aggregateWindow(every: {window_minutes}m, fn: min, createEmpty: true) |> yield(name: "min")
data |> aggregateWindow(every: {window_minutes}m, fn: max, createEmpty: true) |> yield(name: "max")
data |> aggregateWindow(every: {window_minutes}m, fn: last, createEmpty: true) |> yield(name: "last")
data |> aggregateWindow(every: {window_minutes}m, fn: count, createEmpty: true) |> yield(name: "count")'''

    @staticmethod
    def parse_records(tables: Any, *, aggregated: bool) -> dict[str, Any]:
        values: dict[str, dict[str, dict[str, Any]]] = {}
        for table in tables:
            for record in table.records:
                field = record.get_field()
                if field not in {"temperature", "max_rms_vel"}:
                    continue
                timestamp = record.get_time().isoformat().replace("+00:00", "Z")
                item = values.setdefault(timestamp, {}).setdefault(field, {})
                result_name = record.values.get("result") if aggregated else "value"
                value = record.get_value()
                if result_name == "count":
                    item["count"] = int(value or 0)
                else:
                    item[result_name] = float(value) if value is not None else None

        timestamps = sorted(values)

        def build_series(field: str) -> list[dict[str, Any] | None]:
            series = []
            for timestamp in timestamps:
                item = values[timestamp].get(field)
                if not item or (aggregated and not item.get("count", 0)):
                    series.append(None)
                    continue
                if not aggregated:
                    value = item.get("value")
                    series.append(
                        None
                        if value is None
                        else {
                            "value": value,
                            "min": value,
                            "max": value,
                            "last": value,
                            "count": 1,
                        }
                    )
                    continue
                series.append(
                    {
                        "value": item.get("mean"),
                        "min": item.get("min"),
                        "max": item.get("max"),
                        "last": item.get("last"),
                        "count": item.get("count", 0),
                    }
                )
            return series

        return {
            "timestamps": timestamps,
            "temperature": build_series("temperature"),
            "vibration": build_series("max_rms_vel"),
        }

    @classmethod
    def _read_cache(cls, key: str) -> dict[str, Any] | None:
        try:
            raw = redis_manager.get_client().get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.debug("Trend cache read failed for %s: %s", key, exc)
            return None

    @classmethod
    def _write_cache(cls, key: str, value: dict[str, Any]) -> None:
        try:
            redis_manager.get_client().setex(
                key,
                cls.CACHE_SECONDS,
                json.dumps(value, ensure_ascii=False),
            )
        except Exception as exc:
            logger.debug("Trend cache write failed for %s: %s", key, exc)

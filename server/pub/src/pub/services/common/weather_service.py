import asyncio
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import logging
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pub.manager.database import redis_manager
from pub.models.customer import Location, Region, Tenant, TenantSensor
from pub.models.sensor import Sensor, SensorMonitoring
from pub.models.weather import Temperature
from pub.utils.redis_keys import REDIS_KEY_DIA_AMBIENT_TEMP

logger = logging.getLogger(__name__)

SHANGHAI_TZ = timezone(timedelta(hours=8))


class WeatherService:
    @staticmethod
    async def get_region_id_by_tenant(
        session: AsyncSession,
        tenant_id: UUID | None,
    ) -> str | None:
        if tenant_id is None or not hasattr(session, "execute"):
            return None
        try:
            stmt = select(Tenant.region_id).where(Tenant.id == tenant_id)
            return (await session.execute(stmt)).scalar_one_or_none()
        except Exception as exc:
            logger.debug("Failed to resolve region_id for tenant %s: %s", tenant_id, exc)
            return None

    @staticmethod
    async def get_region_id_by_sensor_sn(
        session: AsyncSession,
        sn: str,
    ) -> str | None:
        if not sn or not hasattr(session, "execute"):
            return None
        try:
            stmt = (
                select(Tenant.region_id)
                .join(Location, Location.tenant_id == Tenant.id)
                .join(SensorMonitoring, SensorMonitoring.location_id == Location.id)
                .join(Sensor, Sensor.id == SensorMonitoring.sensor_id)
                .where(Sensor.sn == sn)
                .order_by(SensorMonitoring.status.desc())
            )
            region_id = (await session.execute(stmt)).scalars().first()
            if region_id:
                return str(region_id)

            fallback_stmt = (
                select(Tenant.region_id)
                .join(TenantSensor, TenantSensor.tenant_id == Tenant.id)
                .join(Sensor, Sensor.id == TenantSensor.sensor_id)
                .where(Sensor.sn == sn)
                .order_by(TenantSensor.available.desc())
            )
            region_id = (await session.execute(fallback_stmt)).scalars().first()
            return str(region_id) if region_id else None
        except Exception as exc:
            logger.debug("Failed to resolve region_id for sensor %s: %s", sn, exc)
            return None

    @staticmethod
    async def load_ambient_records(
        session: AsyncSession,
        region_id: str | None,
        start_at_utc: datetime,
        end_at_utc: datetime,
    ) -> list[tuple[datetime, float]]:
        """
        Load ambient temperature records for a region within [start_at_utc, end_at_utc],
        plus the most recent record at or before start_at_utc for forward-fill anchoring.
        Returns sorted list of (utc_datetime, temperature_float).
        """
        if not region_id or not hasattr(session, "execute"):
            return []
        try:
            if start_at_utc.tzinfo is None:
                start_at_utc = start_at_utc.replace(tzinfo=timezone.utc)
            if end_at_utc.tzinfo is None:
                end_at_utc = end_at_utc.replace(tzinfo=timezone.utc)

            start_shanghai = start_at_utc.astimezone(SHANGHAI_TZ).replace(tzinfo=None)
            end_shanghai = end_at_utc.astimezone(SHANGHAI_TZ).replace(tzinfo=None)

            anchor_stmt = (
                select(Temperature.dt, Temperature.temperature)
                .where(
                    Temperature.region_id == str(region_id),
                    Temperature.dt <= start_shanghai,
                )
                .order_by(Temperature.dt.desc())
                .limit(1)
            )
            range_stmt = (
                select(Temperature.dt, Temperature.temperature)
                .where(
                    Temperature.region_id == str(region_id),
                    Temperature.dt > start_shanghai,
                    Temperature.dt <= end_shanghai,
                )
                .order_by(Temperature.dt.asc())
            )

            anchor_rows = (await session.execute(anchor_stmt)).all()
            range_rows = (await session.execute(range_stmt)).all()

            records: list[tuple[datetime, float]] = []
            for row in [*anchor_rows, *range_rows]:
                dt_val, temp_val = row[0], row[1]
                if dt_val is None or temp_val is None:
                    continue
                if dt_val.tzinfo is None:
                    utc_dt = dt_val.replace(tzinfo=SHANGHAI_TZ).astimezone(timezone.utc)
                else:
                    utc_dt = dt_val.astimezone(timezone.utc)
                records.append((utc_dt, round(float(temp_val), 2)))

            records.sort(key=lambda item: item[0])
            return records
        except Exception as exc:
            logger.debug("Failed to load ambient records for region %s: %s", region_id, exc)
            return []

    @staticmethod
    def align_ambient_to_timestamps(
        ambient_records: list[tuple[datetime, float]],
        timestamps: list[str],
        window_minutes: int = 0,
    ) -> list[float | None]:
        """
        Align sparse ambient temperature records onto sensor timestamps using
        window averaging (when multiple ambient samples fall inside an aggregation window)
        and forward-fill (as-of matching for the latest sample <= timestamp).
        """
        if not timestamps:
            return []
        if not ambient_records:
            return [None] * len(timestamps)

        record_times = [item[0] for item in ambient_records]
        record_values = [item[1] for item in ambient_records]
        window_delta = timedelta(minutes=max(0, int(window_minutes or 0)))

        aligned: list[float | None] = []
        for ts_str in timestamps:
            try:
                target_dt = datetime.fromisoformat(
                    str(ts_str).replace("Z", "+00:00")
                )
                if target_dt.tzinfo is None:
                    target_dt = target_dt.replace(tzinfo=timezone.utc)
                else:
                    target_dt = target_dt.astimezone(timezone.utc)
            except Exception:
                aligned.append(None)
                continue

            right_idx = bisect_right(record_times, target_dt)
            if window_minutes and window_minutes > 0:
                window_start = target_dt - window_delta
                left_idx = bisect_right(record_times, window_start)
                if left_idx < right_idx:
                    window_slice = record_values[left_idx:right_idx]
                    aligned.append(round(sum(window_slice) / len(window_slice), 2))
                    continue

            if right_idx > 0:
                aligned.append(record_values[right_idx - 1])
            else:
                # Fallback to earliest available record in the queried range
                aligned.append(record_values[0])

        return aligned

    @staticmethod
    async def fetch_and_store_ambient_temperatures(session: AsyncSession) -> None:
        """
        Fetch ambient temperatures for all active tenants' regions,
        store them in the database, and cache them in Redis.
        """
        # 1. Get unique region_ids from active tenants
        stmt = select(Tenant.region_id).where(Tenant.active == True).distinct()
        result = await session.execute(stmt)
        region_ids = [row[0] for row in result.all()]

        if not region_ids:
            logger.info("No active tenants with regions found. Skipping weather fetch.")
            return

        # 2. Get region details (lat, lng)
        stmt = select(Region).where(Region.id.in_(region_ids))
        result = await session.execute(stmt)
        regions = result.scalars().all()

        redis_client = redis_manager.client

        async with httpx.AsyncClient(timeout=10.0) as client:
            for region in regions:
                if region.lat is None or region.lng is None:
                    logger.warning("Region %s (%s) has no lat/lng. Skipping.", region.id, region.name)
                    continue

                try:
                    # 3. Call Open-Meteo API
                    # Using the free endpoint for current weather
                    url = f"https://api.open-meteo.com/v1/forecast?latitude={region.lat}&longitude={region.lng}&current_weather=true"
                    response = await client.get(url)
                    response.raise_for_status()
                    data = response.json()
                    
                    if "current_weather" in data and "temperature" in data["current_weather"]:
                        temp_celsius = Decimal(str(data["current_weather"]["temperature"]))
                        
                        # 4. Save to Database
                        new_temp = Temperature(
                            region_id=region.id,
                            temperature=temp_celsius
                        )
                        session.add(new_temp)
                        
                        # 5. Save to Redis for diagnosis context
                        if redis_client:
                            cache_key = REDIS_KEY_DIA_AMBIENT_TEMP.format(region_id=region.id)
                            await asyncio.to_thread(redis_client.set, cache_key, str(temp_celsius), ex=7200)
                            logger.debug("Updated ambient temp for region %s to %sC", region.id, temp_celsius)
                    else:
                        logger.error("Unexpected response from Open-Meteo for region %s: %s", region.id, data)
                        
                except Exception as e:
                    logger.error("Failed to fetch weather for region %s (%s): %s", region.id, region.name, str(e))

        # Commit all new temperature records
        try:
            await session.commit()
            logger.debug("Ambient temperatures successfully fetched and stored.")
        except Exception as e:
            await session.rollback()
            logger.error("Failed to commit ambient temperatures to database: %s", str(e))

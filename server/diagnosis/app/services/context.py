import asyncio
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pub.manager.database import db_manager, redis_manager
from pub.models.customer import HealthCheckFreq, IsoStandard, Tenant
from pub.models.device import DeviceCategory, DeviceInst, DeviceSpec, Process, ProcessDevice, ProcessDeviceItem, ProcessItem
from pub.models.sensor import Sensor, SensorMonitoring, SensorThreshold

logger = logging.getLogger(__name__)

DEVICE_CONTEXT_CACHE_PREFIX = "dia:device_context:"

class DeviceContextService:
    """
    Read and cache the relational context needed by diagnosis handlers and data ingestion.
    This service is DEVICE-CENTRIC (keyed by device_id).
    """

    @staticmethod
    async def get_by_device_id(session: AsyncSession, device_id: str) -> dict[str, Any] | None:
        """Return diagnosis context for one device_id, using Redis as read-through cache."""
        cached = await DeviceContextService._get_cached(device_id)
        if cached is not None:
            return cached

        context = await DeviceContextService.build_from_db(session, device_id)
        if context is not None and context.get("configured"):
            await DeviceContextService._set_cached(device_id, context)
        return context

    @staticmethod
    async def get_by_device_id_managed(device_id: str) -> dict[str, Any] | None:
        if db_manager.SessionLocal is None:
            raise RuntimeError("Database not initialized.")
        async with db_manager.SessionLocal() as session:
            return await DeviceContextService.get_by_device_id(session, device_id)

    @staticmethod
    async def build_from_db(session: AsyncSession, device_id: str) -> dict[str, Any] | None:
        """Query MySQL and assemble all diagnosis-related context for one DEVICE."""
        VibThreshold = aliased(SensorThreshold)
        TempThreshold = aliased(SensorThreshold)

        # 1. Fetch core device information
        stmt_device = (
            select(
                DeviceInst,
                DeviceSpec,
                DeviceCategory,
                IsoStandard,
                HealthCheckFreq,
                VibThreshold,
                TempThreshold,
                Tenant,
            )
            .outerjoin(DeviceSpec, DeviceSpec.id == DeviceInst.device_spec_id)
            .outerjoin(DeviceCategory, DeviceCategory.id == DeviceSpec.device_category_id)
            .outerjoin(Tenant, Tenant.id == DeviceCategory.tenant_id)
            .outerjoin(IsoStandard, IsoStandard.id == DeviceCategory.iso_standard_id)
            .outerjoin(HealthCheckFreq, HealthCheckFreq.id == DeviceCategory.health_check_freq_id)
            .outerjoin(VibThreshold, VibThreshold.id == DeviceCategory.vib_threshold_id)
            .outerjoin(TempThreshold, TempThreshold.id == DeviceCategory.temp_threshold_id)
            .where(DeviceInst.id == device_id)
            .limit(1)
        )
        row = (await session.execute(stmt_device)).first()
        if row is None:
            return None

        (
            device_inst,
            device_spec,
            device_category,
            iso_standard,
            health_check,
            vib_threshold,
            temp_threshold,
            tenant,
        ) = row

        # 2. Fetch ALL measuring points (SensorMonitoring) for this device
        stmt_points = (
            select(SensorMonitoring, Sensor)
            .outerjoin(Sensor, Sensor.id == SensorMonitoring.sensor_id)
            .where(
                SensorMonitoring.device_inst_id == device_id,
                SensorMonitoring.status == 1
            )
        )
        points_rows = (await session.execute(stmt_points)).all()
        
        measuring_points = []
        for monitoring, sensor in points_rows:
            measuring_points.append({
                "monitoring_id": str(monitoring.id) if monitoring else None,
                "location_id": str(monitoring.location_id) if monitoring else None,
                "direction": monitoring.direction if monitoring else None,
                "sensor_id": str(sensor.id) if sensor else None,
                "sensor_sn": sensor.sn if sensor else None,
            })

        ambient_temperature = None
        if tenant and tenant.region_id:
            client = _get_redis_client()
            if client:
                try:
                    raw_temp = await asyncio.to_thread(client.get, f"dia:ambient_temperature:{tenant.region_id}")
                    if raw_temp:
                        ambient_temperature = float(raw_temp)
                except Exception as e:
                    logger.warning("Failed to fetch ambient temperature from Redis: %s", str(e))

        return _json_safe({
            "device_id": str(device_inst.id),
            "device_inst": _device_inst_context(device_inst),
            "device_spec": _device_spec_context(device_spec),
            "device_category": _device_category_context(device_category),
            "iso": _iso_context(iso_standard),
            "health_check": _health_check_context(health_check),
            "thresholds": {
                "vibration": _threshold_context(vib_threshold),
                "temperature": _threshold_context(temp_threshold),
            },
            "ambient_temperature": ambient_temperature,
            "measuring_points": measuring_points,
            "configured": device_inst is not None and device_category is not None,
            "cached_at": datetime.utcnow().isoformat(),
        })

    @staticmethod
    async def _get_cached(device_id: str) -> dict[str, Any] | None:
        client = _get_redis_client()
        if client is None: return None
        try:
            raw = await asyncio.to_thread(client.get, f"{DEVICE_CONTEXT_CACHE_PREFIX}{device_id}")
            if not raw: return None
            return json.loads(raw)
        except Exception as e:
            logger.warning("Failed to read context cache for device_id=%s: %s", device_id, e)
            return None

    @staticmethod
    async def _set_cached(device_id: str, context: dict[str, Any]) -> None:
        client = _get_redis_client()
        if client is None: return
        try:
            await asyncio.to_thread(
                client.set,
                f"{DEVICE_CONTEXT_CACHE_PREFIX}{device_id}",
                json.dumps(_json_safe(context), ensure_ascii=False),
            )
        except Exception as e:
            logger.warning("Failed to write context cache for device_id=%s: %s", device_id, e)

def _get_redis_client() -> Any | None:
    try:
        return redis_manager.get_client()
    except Exception:
        return None

def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)

def _device_inst_context(obj): return {"id": obj.id, "name": obj.name, "code": obj.code} if obj else None
def _device_spec_context(obj): return {"id": obj.id, "name": obj.name, "model": obj.model} if obj else None
def _device_category_context(obj): return {"id": obj.id, "name": obj.name} if obj else None
def _iso_context(obj): return {"id": obj.id, "code": obj.code} if obj else None
def _health_check_context(obj): return {"id": obj.id, "patrol": obj.patrol} if obj else None
def _threshold_context(obj): return {"id": obj.id, "code": obj.code, "rt_max_delta": obj.rt_max_delta, "baseline": obj.baseline, "st_max_slope": obj.st_max_slope} if obj else None

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
from pub.models.device import (
    BearingModel,
    DeviceCategory,
    DeviceInst,
    DeviceSpec,
    DeviceSpecBearing,
    Process,
    ProcessDevice,
    ProcessDeviceItem,
    ProcessItem,
)
from pub.models.sensor import Sensor, SensorMonitoring, SensorThreshold
from pub.services.diagnosis.bearing_frequency import calculate_bearing_frequencies
from pub.utils.redis_keys import REDIS_KEY_DIA_PEER_GROUP, REDIS_KEY_DIA_DEVICE_CONTEXT

logger = logging.getLogger(__name__)
DEVICE_CONTEXT_CACHE_TTL_SECONDS = 86400

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

        try:
            device_uuid = UUID(device_id) if isinstance(device_id, str) else device_id
        except ValueError:
            return None

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
            )
            .outerjoin(DeviceSpec, DeviceSpec.id == DeviceInst.device_spec_id)
            .outerjoin(DeviceCategory, DeviceCategory.id == DeviceSpec.device_category_id)
            .outerjoin(IsoStandard, IsoStandard.id == DeviceCategory.iso_standard_id)
            .outerjoin(HealthCheckFreq, HealthCheckFreq.id == DeviceCategory.health_check_freq_id)
            .outerjoin(VibThreshold, VibThreshold.id == DeviceCategory.vib_threshold_id)
            .outerjoin(TempThreshold, TempThreshold.id == DeviceCategory.temp_threshold_id)
            .where(DeviceInst.id == device_uuid)
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
        ) = row

        # 2. Fetch ALL measuring points (SensorMonitoring) for this device
        stmt_points = (
            select(SensorMonitoring, Sensor)
            .outerjoin(Sensor, Sensor.id == SensorMonitoring.sensor_id)
            .where(
                SensorMonitoring.device_inst_id == device_uuid,
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

        bearing_bindings = await _build_bearing_bindings(
            session,
            device_spec,
            device_category.tenant_id if device_category is not None else None,
        )

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
            "measuring_points": measuring_points,
            "bearing_bindings": bearing_bindings,
            "configured": device_inst is not None and device_category is not None,
            "cached_at": datetime.utcnow().isoformat(),
        })

    @staticmethod
    async def _get_cached(device_id: str) -> dict[str, Any] | None:
        client = _get_redis_client()
        if client is None: return None
        try:
            key = REDIS_KEY_DIA_DEVICE_CONTEXT.format(device_id=device_id)
            raw = await asyncio.to_thread(client.get, key)
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
            key = REDIS_KEY_DIA_DEVICE_CONTEXT.format(device_id=device_id)
            await asyncio.to_thread(
                client.set,
                key,
                json.dumps(_json_safe(context), ensure_ascii=False),
                ex=DEVICE_CONTEXT_CACHE_TTL_SECONDS,
            )
        except Exception as e:
            logger.warning("Failed to write context cache for device_id=%s: %s", device_id, e)

    @staticmethod
    async def invalidate_by_device_id(device_id: str) -> None:
        await DeviceContextService.invalidate_by_device_ids([device_id])

    @staticmethod
    async def invalidate_by_device_ids(device_ids: list[str]) -> None:
        unique_ids = sorted({str(device_id) for device_id in device_ids if device_id})
        if not unique_ids:
            return
        client = _get_redis_client()
        if client is None:
            return
        keys = [
            REDIS_KEY_DIA_DEVICE_CONTEXT.format(device_id=device_id)
            for device_id in unique_ids
        ]
        try:
            await asyncio.to_thread(client.delete, *keys)
            logger.info("Invalidated device context cache for device_ids=%s", unique_ids)
        except Exception as e:
            logger.warning(
                "Failed to invalidate device context cache for device_ids=%s: %s",
                unique_ids,
                e,
            )

    @staticmethod
    async def get_peer_group_managed(process_device_id: str, device_category_id: str) -> list[dict[str, Any]]:
        """Fetch the peer group from Redis, or build it from DB and cache it."""
        if not process_device_id or not device_category_id:
            return []
            
        client = _get_redis_client()
        cache_key = REDIS_KEY_DIA_PEER_GROUP.format(process_device_id=process_device_id, device_category_id=device_category_id)
        
        if client:
            try:
                raw = await asyncio.to_thread(client.get, cache_key)
                if raw:
                    return json.loads(raw)
            except Exception as e:
                logger.warning("Failed to read peer group cache: %s", e)
                
        if db_manager.SessionLocal is None:
            return []
            
        import uuid
        try:
            pd_uuid = uuid.UUID(process_device_id)
            dc_uuid = uuid.UUID(device_category_id)
        except Exception:
            return []
            
        async with db_manager.SessionLocal() as session:
            # Join ProcessDeviceItem -> DeviceInst -> SensorMonitoring to get all location_ids
            # Ensure they share the same device_category_id
            stmt = (
                select(SensorMonitoring.location_id, DeviceInst.id.label("device_inst_id"))
                .join(DeviceInst, DeviceInst.id == SensorMonitoring.device_inst_id)
                .join(DeviceSpec, DeviceSpec.id == DeviceInst.device_spec_id)
                .join(ProcessDeviceItem, ProcessDeviceItem.device_inst_id == DeviceInst.id)
                .where(
                    ProcessDeviceItem.process_device_id == pd_uuid,
                    DeviceSpec.device_category_id == dc_uuid,
                    SensorMonitoring.status == 1
                )
            )
            rows = (await session.execute(stmt)).all()
            
            peers = [{"location_id": str(r.location_id), "device_inst_id": str(r.device_inst_id)} for r in rows if r.location_id]
            
            if client and peers:
                try:
                    await asyncio.to_thread(client.set, cache_key, json.dumps(peers, ensure_ascii=False), ex=86400) # Cache for 1 day
                except Exception as e:
                    logger.warning("Failed to write peer group cache: %s", e)
            
            return peers


async def _build_bearing_bindings(
    session: AsyncSession,
    device_spec: DeviceSpec | None,
    tenant_id: UUID | None,
) -> list[dict[str, Any]]:
    if device_spec is None or tenant_id is None:
        return []
    stmt = (
        select(DeviceSpecBearing, BearingModel)
        .join(BearingModel, BearingModel.id == DeviceSpecBearing.bearing_id)
        .where(
            DeviceSpecBearing.device_spec_id == device_spec.id,
            BearingModel.tenant_id == tenant_id,
            DeviceSpecBearing.enabled.is_(True),
            BearingModel.active.is_(True),
        )
        .order_by(DeviceSpecBearing.location_id, BearingModel.brand, BearingModel.model)
    )
    rows = (await session.execute(stmt)).all()
    return [
        _bearing_binding_context(binding, bearing, device_spec.rpm)
        for binding, bearing in rows
    ]


def _bearing_binding_context(
    binding: DeviceSpecBearing,
    bearing: BearingModel,
    rpm: Any,
) -> dict[str, Any]:
    result = {
        "id": binding.id,
        "device_spec_id": binding.device_spec_id,
        "bearing_id": binding.bearing_id,
        "location_id": binding.location_id,
        "shaft_speed_ratio": binding.shaft_speed_ratio,
        "enabled": binding.enabled,
        "bearing": {
            "id": bearing.id,
            "tenant_id": bearing.tenant_id,
            "brand": bearing.brand,
            "model": bearing.model,
            "bearing_type": bearing.bearing_type,
            "rolling_element_count": bearing.rolling_element_count,
            "rolling_element_diameter_mm": bearing.rolling_element_diameter_mm,
            "pitch_diameter_mm": bearing.pitch_diameter_mm,
            "contact_angle_deg": bearing.contact_angle_deg,
            "description": bearing.description,
            "active": bearing.active,
        },
    }
    try:
        result["frequency_reference_hz"] = calculate_bearing_frequencies(
            rpm=rpm,
            rolling_element_count=bearing.rolling_element_count,
            rolling_element_diameter_mm=bearing.rolling_element_diameter_mm,
            pitch_diameter_mm=bearing.pitch_diameter_mm,
            contact_angle_deg=bearing.contact_angle_deg,
            shaft_speed_ratio=binding.shaft_speed_ratio,
        )
        result["frequency_validation_error"] = None
    except ValueError as exc:
        result["frequency_reference_hz"] = None
        result["frequency_validation_error"] = str(exc)
    return result

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
def _device_spec_context(obj): return {"id": obj.id, "name": obj.name, "model": obj.model, "rpm": obj.rpm} if obj else None
def _device_category_context(obj): return {"id": obj.id, "name": obj.name} if obj else None
def _iso_context(obj): return {"id": obj.id, "code": obj.code} if obj else None
def _health_check_context(obj): return {"id": obj.id, "patrol": obj.patrol} if obj else None
def _threshold_context(obj): 
    return {
        "id": obj.id, 
        "code": obj.code, 
        "rt_max_delta": obj.rt_max_delta, 
        "baseline": obj.baseline, 
        "st_max_slope": obj.st_max_slope,
        "st_max_amplitude": obj.st_max_amplitude,
        "mt_max_slope": obj.mt_max_slope,
        "mt_max_amplitude": obj.mt_max_amplitude
    } if obj else None

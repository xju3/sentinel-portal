"""
Diagnosis context lookup and Redis cache.

The diagnosis pipeline needs low-frequency relational context for every report:
sensor binding, monitoring direction, device category, ISO standard, thresholds,
and check frequency. This module keeps that lookup in one place and exposes a
per-SN Redis cache so metric handlers do not repeat the same MySQL joins.
"""

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

from pub.database import db_manager, redis_manager
from pub.models.customer import HealthCheckFreq, IsoStandard
from pub.models.device import DeviceCategory, DeviceInst, DeviceSpec
from pub.models.sensor import Sensor, SensorMonitoring, SensorThreshold

logger = logging.getLogger(__name__)

DIAGNOSIS_CONTEXT_CACHE_PREFIX = "dia:diagnosis_context:"


class DiagnosisContextService:
    """Read and cache the relational context needed by diagnosis handlers."""

    @staticmethod
    async def get_by_sn(session: AsyncSession, sn: str) -> dict[str, Any] | None:
        """Return diagnosis context for one sensor SN, using Redis as read-through cache."""
        cached = await DiagnosisContextService._get_cached(sn)
        if cached is not None:
            return cached

        context = await DiagnosisContextService.build_from_db(session, sn)
        if context is not None and context.get("configured"):
            await DiagnosisContextService._set_cached(sn, context)
        return context

    @staticmethod
    async def get_by_sn_managed(sn: str) -> dict[str, Any] | None:
        """Return diagnosis context using an internally managed DB session."""
        if db_manager.SessionLocal is None:
            raise RuntimeError("Database not initialized. Call db_manager.init() first.")

        async with db_manager.SessionLocal() as session:
            return await DiagnosisContextService.get_by_sn(session, sn)

    @staticmethod
    async def build_from_db(session: AsyncSession, sn: str) -> dict[str, Any] | None:
        """Query MySQL and assemble all diagnosis-related context for one SN."""
        VibThreshold = aliased(SensorThreshold)
        TempThreshold = aliased(SensorThreshold)

        stmt = (
            select(
                Sensor,
                SensorMonitoring,
                DeviceInst,
                DeviceSpec,
                DeviceCategory,
                IsoStandard,
                HealthCheckFreq,
                VibThreshold,
                TempThreshold,
            )
            .select_from(Sensor)
            .outerjoin(
                SensorMonitoring,
                (SensorMonitoring.sensor_id == Sensor.id) & (SensorMonitoring.status == 1),
            )
            .outerjoin(DeviceInst, DeviceInst.id == SensorMonitoring.device_inst_id)
            .outerjoin(DeviceSpec, DeviceSpec.id == DeviceInst.device_spec_id)
            .outerjoin(DeviceCategory, DeviceCategory.id == DeviceSpec.device_category_id)
            .outerjoin(IsoStandard, IsoStandard.id == DeviceCategory.iso_standard_id)
            .outerjoin(HealthCheckFreq, HealthCheckFreq.id == DeviceCategory.health_check_freq_id)
            .outerjoin(VibThreshold, VibThreshold.id == DeviceCategory.vib_threshold_id)
            .outerjoin(TempThreshold, TempThreshold.id == DeviceCategory.temp_threshold_id)
            .where(Sensor.sn == sn)
            .order_by(SensorMonitoring.ts.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        row = result.first()
        if row is None:
            return None

        (
            sensor,
            monitoring,
            device_inst,
            device_spec,
            device_category,
            iso_standard,
            health_check,
            vib_threshold,
            temp_threshold,
        ) = row

        return _json_safe({
            "sn": sensor.sn,
            "sensor": _sensor_context(sensor),
            "monitoring": _monitoring_context(monitoring),
            "device_inst": _device_inst_context(device_inst),
            "device_spec": _device_spec_context(device_spec),
            "device_category": _device_category_context(device_category),
            "iso": _iso_context(iso_standard),
            "health_check": _health_check_context(health_check),
            "thresholds": {
                "vibration": _threshold_context(vib_threshold),
                "temperature": _threshold_context(temp_threshold),
            },
            "configured": monitoring is not None and device_inst is not None and device_category is not None,
            "cached_at": datetime.utcnow().isoformat(),
        })

    @staticmethod
    async def invalidate_by_sn(sn: str) -> None:
        """Delete the cached diagnosis context for one SN."""
        if not sn:
            return
        await DiagnosisContextService._delete_cache_key(_cache_key(sn))

    @staticmethod
    async def invalidate_by_sns(sns: list[str]) -> None:
        """Delete cached diagnosis contexts for multiple SNs."""
        unique_sns = sorted({sn for sn in sns if sn})
        if not unique_sns:
            return

        keys = [_cache_key(sn) for sn in unique_sns]
        client = _get_redis_client()
        if client is None:
            return

        try:
            await asyncio.to_thread(client.delete, *keys)
            logger.info("Invalidated diagnosis context cache for SNs: %s", unique_sns)
        except Exception as e:
            logger.warning("Failed to invalidate diagnosis context cache for SNs=%s: %s", unique_sns, e)

    @staticmethod
    async def _get_cached(sn: str) -> dict[str, Any] | None:
        client = _get_redis_client()
        if client is None:
            return None

        try:
            raw = await asyncio.to_thread(client.get, _cache_key(sn))
        except Exception as e:
            logger.warning("Failed to read diagnosis context cache for sn=%s: %s", sn, e)
            return None

        if not raw:
            return None

        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            await DiagnosisContextService.invalidate_by_sn(sn)
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    async def _set_cached(sn: str, context: dict[str, Any]) -> None:
        client = _get_redis_client()
        if client is None:
            return

        try:
            await asyncio.to_thread(
                client.set,
                _cache_key(sn),
                json.dumps(_json_safe(context), ensure_ascii=False),
            )
        except Exception as e:
            logger.warning("Failed to write diagnosis context cache for sn=%s: %s", sn, e)

    @staticmethod
    async def _delete_cache_key(key: str) -> None:
        client = _get_redis_client()
        if client is None:
            return
        try:
            await asyncio.to_thread(client.delete, key)
        except Exception as e:
            logger.warning("Failed to delete diagnosis context cache key=%s: %s", key, e)


def _cache_key(sn: str) -> str:
    return f"{DIAGNOSIS_CONTEXT_CACHE_PREFIX}{sn}"


def _get_redis_client() -> Any | None:
    try:
        return redis_manager.get_client()
    except Exception:
        logger.debug("Redis is not initialized; diagnosis context cache unavailable")
        return None


def _sensor_context(sensor: Sensor) -> dict[str, Any]:
    return {
        "id": sensor.id,
        "sn": sensor.sn,
        "active": sensor.active,
        "sensor_batch_id": sensor.sensor_batch_id,
    }


def _monitoring_context(monitoring: SensorMonitoring | None) -> dict[str, Any] | None:
    if monitoring is None:
        return None
    return {
        "id": monitoring.id,
        "device_inst_id": monitoring.device_inst_id,
        "location_id": monitoring.location_id,
        "sensor_id": monitoring.sensor_id,
        "direction": monitoring.direction,
        "status": monitoring.status,
    }


def _device_inst_context(device_inst: DeviceInst | None) -> dict[str, Any] | None:
    if device_inst is None:
        return None
    return {
        "id": device_inst.id,
        "name": device_inst.name,
        "code": device_inst.code,
        "status": device_inst.status,
        "active": device_inst.active,
        "available": device_inst.available,
        "device_spec_id": device_inst.device_spec_id,
    }


def _device_spec_context(device_spec: DeviceSpec | None) -> dict[str, Any] | None:
    if device_spec is None:
        return None
    return {
        "id": device_spec.id,
        "name": device_spec.name,
        "model": device_spec.model,
        "brand": device_spec.brand,
        "rpm": device_spec.rpm,
        "device_category_id": device_spec.device_category_id,
    }


def _device_category_context(device_category: DeviceCategory | None) -> dict[str, Any] | None:
    if device_category is None:
        return None
    return {
        "id": device_category.id,
        "name": device_category.name,
        "tenant_id": device_category.tenant_id,
        "iso_standard_id": device_category.iso_standard_id,
        "vib_threshold_id": device_category.vib_threshold_id,
        "temp_threshold_id": device_category.temp_threshold_id,
        "health_check_freq_id": device_category.health_check_freq_id,
    }


def _iso_context(iso_standard: IsoStandard | None) -> dict[str, Any] | None:
    if iso_standard is None:
        return None
    return {
        "id": iso_standard.id,
        "code": iso_standard.code,
        "version": iso_standard.version,
        "category": iso_standard.category,
        "foundation": iso_standard.foundation,
        "description": iso_standard.description,
    }


def _health_check_context(health_check: HealthCheckFreq | None) -> dict[str, Any] | None:
    if health_check is None:
        return None
    return {
        "id": health_check.id,
        "patrol": health_check.patrol,
        "diagnosis": health_check.diagnosis,
        "report": health_check.report,
        "status": health_check.status,
    }


def _threshold_context(threshold: SensorThreshold | None) -> dict[str, Any] | None:
    if threshold is None:
        return None
    return {
        "id": threshold.id,
        "code": threshold.code,
        "metric": threshold.metric,
        "rt_max_delta": threshold.rt_max_delta,
        "st_max_slope": threshold.st_max_slope,
        "st_max_amplitude": threshold.st_max_amplitude,
        "mt_max_slope": threshold.mt_max_slope,
        "mt_max_amplitude": threshold.mt_max_amplitude,
        "baseline": threshold.baseline,
        "tenant_id": threshold.tenant_id,
    }


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

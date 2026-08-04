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

from pub.manager.database import db_manager, redis_manager
from pub.models.customer import HealthCheckFreq, IsoStandard
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
from pub.utils.redis_keys import REDIS_KEY_DIA_DIAGNOSIS_CONTEXT

logger = logging.getLogger(__name__)

DIAGNOSIS_CONTEXT_CACHE_TTL_SECONDS = 86400


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

        peer_group = None
        if monitoring is not None and device_inst is not None and device_spec is not None:
            peer_group = await DiagnosisContextService._build_peer_group_context(
                session=session,
                device_inst=device_inst,
                device_spec=device_spec,
                monitoring=monitoring,
            )
        bearing_bindings = await DiagnosisContextService._build_bearing_bindings(
            session,
            device_spec,
            device_category.tenant_id if device_category is not None else None,
            monitoring.location_id if monitoring is not None else None,
        )

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
            "peer_group": peer_group,
            "bearing_bindings": bearing_bindings,
            "configured": monitoring is not None and device_inst is not None and device_category is not None,
            "cached_at": datetime.utcnow().isoformat(),
        })

    @staticmethod
    async def _build_bearing_bindings(
        session: AsyncSession,
        device_spec: DeviceSpec | None,
        tenant_id: UUID | None,
        location_id: UUID | None,
    ) -> list[dict[str, Any]]:
        if device_spec is None or tenant_id is None or location_id is None:
            return []
        stmt = (
            select(DeviceSpecBearing, BearingModel)
            .join(BearingModel, BearingModel.id == DeviceSpecBearing.bearing_id)
            .where(
                DeviceSpecBearing.device_spec_id == device_spec.id,
                DeviceSpecBearing.location_id == location_id,
                BearingModel.tenant_id == tenant_id,
                DeviceSpecBearing.enabled.is_(True),
                BearingModel.active.is_(True),
            )
            .order_by(BearingModel.brand, BearingModel.model)
        )
        rows = (await session.execute(stmt)).all()
        return [
            _bearing_binding_context(binding, bearing, device_spec.rpm)
            for binding, bearing in rows
        ]

    @staticmethod
    async def _build_peer_group_context(
        session: AsyncSession,
        device_inst: DeviceInst,
        device_spec: DeviceSpec,
        monitoring: SensorMonitoring,
    ) -> dict[str, Any]:
        """Build the same-process same-spec peer group used for horizontal diagnosis."""
        stmt_process_device = (
            select(ProcessDeviceItem, ProcessDevice, Process)
            .join(ProcessDevice, ProcessDevice.id == ProcessDeviceItem.process_device_id)
            .join(Process, Process.id == ProcessDevice.process_id)
            .where(ProcessDeviceItem.device_inst_id == device_inst.id)
            .limit(1)
        )
        process_row = (await session.execute(stmt_process_device)).first()
        if process_row is None:
            return {
                "enabled": False,
                "reason": "device_not_in_process_device",
                "current_device_inst_id": device_inst.id,
                "current_monitoring_id": monitoring.id,
                "device_spec_id": device_spec.id,
                "expected_qty": None,
                "members": [],
            }

        process_device_item, process_device, process = process_row
        stmt_process_item = (
            select(ProcessItem)
            .where(
                ProcessItem.process_id == process.id,
                ProcessItem.device_spec_id == device_spec.id,
            )
            .limit(1)
        )
        process_item = (await session.execute(stmt_process_item)).scalar_one_or_none()
        expected_qty = process_item.qty if process_item is not None else None
        if expected_qty is None:
            enabled = False
            reason = "process_item_not_configured"
        elif expected_qty <= 1:
            enabled = False
            reason = "single_device_required"
        else:
            enabled = True
            reason = None

        members = await DiagnosisContextService._query_peer_group_members(
            session=session,
            process_device_id=process_device.id,
            device_spec_id=device_spec.id,
        )

        comparable_member_count = len({
            member["device_inst"]["id"]
            for member in members
            if member.get("sensor") is not None and member.get("monitoring") is not None
        })
        if enabled and comparable_member_count < 2:
            enabled = False
            reason = "not_enough_configured_peers"

        return {
            "enabled": enabled,
            "reason": reason,
            "process": _process_context(process),
            "process_device": _process_device_context(process_device),
            "process_device_item": _process_device_item_context(process_device_item),
            "process_item": _process_item_context(process_item),
            "current_device_inst_id": device_inst.id,
            "current_monitoring_id": monitoring.id,
            "device_spec_id": device_spec.id,
            "expected_qty": expected_qty,
            "comparable_member_count": comparable_member_count,
            "members": members,
        }

    @staticmethod
    async def _query_peer_group_members(
        session: AsyncSession,
        process_device_id: UUID,
        device_spec_id: UUID,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(
                ProcessDeviceItem,
                DeviceInst,
                SensorMonitoring,
                Sensor,
            )
            .join(DeviceInst, DeviceInst.id == ProcessDeviceItem.device_inst_id)
            .outerjoin(
                SensorMonitoring,
                (SensorMonitoring.device_inst_id == DeviceInst.id) & (SensorMonitoring.status == 1),
            )
            .outerjoin(Sensor, Sensor.id == SensorMonitoring.sensor_id)
            .where(
                ProcessDeviceItem.process_device_id == process_device_id,
                DeviceInst.device_spec_id == device_spec_id,
            )
            .order_by(ProcessDeviceItem.code, DeviceInst.code, SensorMonitoring.direction)
        )
        rows = await session.execute(stmt)
        members: list[dict[str, Any]] = []
        for process_device_item, device_inst, monitoring, sensor in rows:
            members.append({
                "process_device_item": _process_device_item_context(process_device_item),
                "device_inst": _device_inst_context(device_inst),
                "monitoring": _monitoring_context(monitoring),
                "sensor": _sensor_context(sensor) if sensor is not None else None,
            })
        return members

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
                ex=DIAGNOSIS_CONTEXT_CACHE_TTL_SECONDS,
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
    return REDIS_KEY_DIA_DIAGNOSIS_CONTEXT.format(sn=sn)


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


def _process_context(process: Process | None) -> dict[str, Any] | None:
    if process is None:
        return None
    return {
        "id": process.id,
        "tenant_id": process.tenant_id,
        "code": process.code,
        "name": process.name,
        "status": process.status,
    }


def _process_item_context(process_item: ProcessItem | None) -> dict[str, Any] | None:
    if process_item is None:
        return None
    return {
        "id": process_item.id,
        "process_id": process_item.process_id,
        "device_spec_id": process_item.device_spec_id,
        "qty": process_item.qty,
    }


def _process_device_context(process_device: ProcessDevice | None) -> dict[str, Any] | None:
    if process_device is None:
        return None
    return {
        "id": process_device.id,
        "code": process_device.code,
        "process_id": process_device.process_id,
        "sn": process_device.sn,
        "status": process_device.status,
        "area_id": process_device.area_id,
    }


def _process_device_item_context(process_device_item: ProcessDeviceItem | None) -> dict[str, Any] | None:
    if process_device_item is None:
        return None
    return {
        "id": process_device_item.id,
        "code": process_device_item.code,
        "desc": process_device_item.desc,
        "device_inst_id": process_device_item.device_inst_id,
        "process_device_id": process_device_item.process_device_id,
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

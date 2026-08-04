"""Tenant-scoped bearing model and device-spec binding operations."""

import asyncio
import logging
import math
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pub.manager.database import redis_manager
from pub.models.customer import Location
from pub.models.device import BearingModel, DeviceInst, DeviceSpecBearing
from pub.models.sensor import Sensor, SensorMonitoring
from pub.services.device.device_spec_service import DeviceSpecService
from pub.utils.redis_keys import (
    REDIS_KEY_DIA_DEVICE_CONTEXT,
    REDIS_KEY_DIA_DIAGNOSIS_CONTEXT,
)

logger = logging.getLogger(__name__)

class BearingConflictError(ValueError):
    """A concurrent or persisted binding conflicts with the requested write."""


class BearingService:
    ConflictError = BearingConflictError

    @staticmethod
    async def list_models(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[BearingModel]:
        result = await session.execute(
            select(BearingModel)
            .where(BearingModel.tenant_id == tenant_id)
            .order_by(BearingModel.brand, BearingModel.model)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_model(
        session: AsyncSession,
        tenant_id: UUID,
        bearing_id: UUID,
    ) -> BearingModel | None:
        result = await session.execute(
            select(BearingModel).where(
                BearingModel.id == bearing_id,
                BearingModel.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def find_duplicate(
        session: AsyncSession,
        tenant_id: UUID,
        brand: str,
        model: str,
        exclude_id: UUID | None = None,
    ) -> BearingModel | None:
        stmt = select(BearingModel).where(
            BearingModel.tenant_id == tenant_id,
            func.lower(BearingModel.brand) == brand.casefold(),
            func.lower(BearingModel.model) == model.casefold(),
        )
        if exclude_id is not None:
            stmt = stmt.where(BearingModel.id != exclude_id)
        result = await session.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_model(
        session: AsyncSession,
        tenant_id: UUID,
        data: dict[str, Any],
    ) -> BearingModel:
        BearingService._validate_geometry(data)
        obj = BearingModel(tenant_id=tenant_id, **data)
        session.add(obj)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise ValueError(
                "A bearing with the same brand and model already exists"
            ) from exc
        await session.refresh(obj)
        return obj

    @staticmethod
    async def update_model(
        session: AsyncSession,
        obj: BearingModel,
        data: dict[str, Any],
    ) -> BearingModel:
        affected_specs = await BearingService._spec_ids_for_bearing(session, obj.id)
        complete_data = {
            "rolling_element_count": obj.rolling_element_count,
            "rolling_element_diameter_mm": obj.rolling_element_diameter_mm,
            "pitch_diameter_mm": obj.pitch_diameter_mm,
            "contact_angle_deg": obj.contact_angle_deg,
            **data,
        }
        BearingService._validate_geometry(complete_data)
        for key, value in data.items():
            setattr(obj, key, value)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise ValueError(
                "A bearing with the same brand and model already exists"
            ) from exc
        await session.refresh(obj)
        await BearingService.invalidate_diagnosis_cache(session, affected_specs)
        return obj

    @staticmethod
    async def delete_model(session: AsyncSession, obj: BearingModel) -> None:
        bound = await session.execute(
            select(DeviceSpecBearing.id)
            .where(DeviceSpecBearing.bearing_id == obj.id)
            .limit(1)
        )
        if bound.scalar_one_or_none() is not None:
            raise ValueError("Bearing model is bound to one or more device specs")
        await session.delete(obj)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise BearingConflictError(
                "Bearing model became bound and cannot be deleted"
            ) from exc

    @staticmethod
    async def list_bindings(
        session: AsyncSession,
        tenant_id: UUID,
        device_spec_id: UUID,
    ) -> list[DeviceSpecBearing] | None:
        if not await DeviceSpecService.is_tenant_device_spec(
            session, tenant_id, device_spec_id
        ):
            return None
        result = await session.execute(
            select(DeviceSpecBearing)
            .join(BearingModel, BearingModel.id == DeviceSpecBearing.bearing_id)
            .options(
                selectinload(DeviceSpecBearing.bearing),
                selectinload(DeviceSpecBearing.location),
            )
            .where(
                DeviceSpecBearing.device_spec_id == device_spec_id,
                BearingModel.tenant_id == tenant_id,
            )
            .order_by(DeviceSpecBearing.location_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def replace_bindings(
        session: AsyncSession,
        tenant_id: UUID,
        device_spec_id: UUID,
        bindings: list[dict[str, Any]],
    ) -> list[DeviceSpecBearing] | None:
        if not await DeviceSpecService.is_tenant_device_spec(
            session, tenant_id, device_spec_id
        ):
            return None

        bearing_ids = {binding["bearing_id"] for binding in bindings}
        if bearing_ids:
            owned_result = await session.execute(
                select(BearingModel.id).where(
                    BearingModel.id.in_(bearing_ids),
                    BearingModel.tenant_id == tenant_id,
                    BearingModel.active.is_(True),
                )
            )
            owned_ids = set(owned_result.scalars().all())
            if owned_ids != bearing_ids:
                raise ValueError(
                    "Every bearing_id must reference an active bearing owned by current tenant"
                )

        location_ids = {binding["location_id"] for binding in bindings}
        if len(location_ids) != len(bindings):
            raise ValueError("Bearing locations must be unique within a device spec")
        if location_ids:
            location_result = await session.execute(
                select(Location.id).where(
                    Location.id.in_(location_ids),
                    Location.tenant_id == tenant_id,
                    Location.is_bearing_point.is_(True),
                    Location.status == 1,
                )
            )
            owned_location_ids = set(location_result.scalars().all())
            if owned_location_ids != location_ids:
                raise ValueError(
                    "Every location_id must reference an active bearing point owned by current tenant"
                )
        for binding in bindings:
            BearingService._validate_binding(binding)

        await session.execute(
            delete(DeviceSpecBearing).where(
                DeviceSpecBearing.device_spec_id == device_spec_id
            )
        )
        session.add_all(
            [
                DeviceSpecBearing(device_spec_id=device_spec_id, **binding)
                for binding in bindings
            ]
        )
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise BearingConflictError(
                "Bearing bindings conflict with current configuration"
            ) from exc
        await BearingService.invalidate_diagnosis_cache(session, [device_spec_id])
        return await BearingService.list_bindings(session, tenant_id, device_spec_id)

    @staticmethod
    async def _spec_ids_for_bearing(
        session: AsyncSession,
        bearing_id: UUID,
    ) -> list[UUID]:
        result = await session.execute(
            select(DeviceSpecBearing.device_spec_id).where(
                DeviceSpecBearing.bearing_id == bearing_id
            )
        )
        return list(set(result.scalars().all()))

    @staticmethod
    def _validate_geometry(data: dict[str, Any]) -> None:
        count = int(data["rolling_element_count"])
        element_diameter = float(data["rolling_element_diameter_mm"])
        pitch_diameter = float(data["pitch_diameter_mm"])
        angle = float(data.get("contact_angle_deg", 0.0))
        if not all(
            math.isfinite(value)
            for value in (element_diameter, pitch_diameter, angle)
        ):
            raise ValueError("bearing geometry values must be finite")
        if not 3 <= count <= 1000:
            raise ValueError("rolling_element_count must be between 3 and 1000")
        if element_diameter <= 0 or pitch_diameter <= element_diameter:
            raise ValueError(
                "rolling_element_diameter_mm must be positive and less than pitch_diameter_mm"
            )
        if not 0 <= angle < 90:
            raise ValueError("contact_angle_deg must be in the range [0, 90)")

    @staticmethod
    def _validate_binding(binding: dict[str, Any]) -> None:
        ratio = float(binding.get("shaft_speed_ratio", 1.0))
        if not math.isfinite(ratio):
            raise ValueError("shaft_speed_ratio must be finite")
        if not 0 < ratio <= 1000:
            raise ValueError("shaft_speed_ratio must be in the range (0, 1000]")

    @staticmethod
    async def invalidate_diagnosis_cache(
        session: AsyncSession,
        device_spec_ids: list[UUID],
    ) -> None:
        """Invalidate only server-side diagnosis context; no firmware task is created."""
        if not device_spec_ids:
            return

        device_result = await session.execute(
            select(DeviceInst.id).where(
                DeviceInst.device_spec_id.in_(device_spec_ids)
            )
        )
        device_ids = list(device_result.scalars().all())
        sensor_result = await session.execute(
            select(Sensor.sn)
            .select_from(DeviceInst)
            .join(
                SensorMonitoring,
                (SensorMonitoring.device_inst_id == DeviceInst.id)
                & (SensorMonitoring.status == 1),
            )
            .outerjoin(Sensor, Sensor.id == SensorMonitoring.sensor_id)
            .where(DeviceInst.device_spec_id.in_(device_spec_ids))
        )
        keys = {
            REDIS_KEY_DIA_DEVICE_CONTEXT.format(device_id=device_id)
            for device_id in device_ids
        }
        keys.update(
            REDIS_KEY_DIA_DIAGNOSIS_CONTEXT.format(sn=sn)
            for sn in sensor_result.scalars().all()
            if sn
        )
        if not keys:
            return

        try:
            client = redis_manager.get_client()
        except Exception:
            logger.debug("Redis is not initialized; diagnosis cache invalidation skipped")
            return
        if client is None:
            return
        try:
            await asyncio.to_thread(client.delete, *sorted(keys))
        except Exception as exc:
            logger.warning("Failed to invalidate bearing diagnosis cache: %s", exc)

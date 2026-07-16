"""
Sensor service - business logic for sensor operations
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.query_api import QueryApi

from pub.manager.database import influxdb_manager, db_manager
from fastapi import BackgroundTasks
from pub.models.sensor import SensorType, Sensor, SensorBatch, SensorThreshold, SensorMonitoring, SimCard
from pub.models.device import DeviceInst, DeviceSpec, DeviceCategory, ProcessDeviceItem, ProcessDevice
from pub.models.customer import Tenant, Area, HealthCheckFreq, IsoStandard, Region
from pub.exceptions.domain_exception import DomainException
from pub.utils.sorting import apply_sorting
logger = logging.getLogger(__name__)

class SensorConfigService:
    """Service for building device-side default_config.json from database."""

    @staticmethod
    async def get_config_by_sn(session: AsyncSession, sn: str) -> Optional[dict]:
        """Fetch the full device configuration for a given sensor SN.

        Returns a dict matching the structure of docs/default_config.json,
        or None if the sensor is not found / not linked to any monitoring record.
        """
        # 1. Find the Sensor and its active SensorMonitoring record
        stmt = (
            select(Sensor, SensorMonitoring, SensorBatch, SensorType)
            .outerjoin(SensorMonitoring, Sensor.id == SensorMonitoring.sensor_id)
            .outerjoin(SensorBatch, Sensor.sensor_batch_id == SensorBatch.id)
            .outerjoin(SensorType, SensorBatch.sensor_type_id == SensorType.id)
            .where(Sensor.sn == sn)
        )
        result = await session.execute(stmt)
        row = result.first()

        if not row:
            return None

        sensor, monitoring, batch, sensor_type = row

        # Defaults that mirror default_config.json
        config = {
            "iso": {"standard": 1, "category": 3, "foundation": 1},
            "rpm": 1480,
            "voltage": 19000,
            "host": "",
            "patrol": 60,
            "diagnosis": 1440,
            "report": 1,
            "network": 1,
            "wifi": {"ssid": "", "pass": ""},
            "configured": False,
        }

        # Early exit if no monitoring record or no device_inst
        if not monitoring or not monitoring.device_inst_id:
            return config

        # 2. Load device-side chain: DeviceInst → DeviceSpec → DeviceCategory
        stmt2 = (
            select(DeviceInst, DeviceSpec, DeviceCategory)
            .outerjoin(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
            .outerjoin(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
            .where(DeviceInst.id == monitoring.device_inst_id)
        )
        result2 = await session.execute(stmt2)
        device_row = result2.first()
        if not device_row:
            return config

        device_inst, device_spec, device_cat = device_row

        # 3. rpm from DeviceSpec
        if device_spec and device_spec.rpm is not None:
            config["rpm"] = device_spec.rpm

        if not device_cat:
            return config

        iso = None
        hcf = None
        tenant = None

        # 4. ISO standard
        if device_cat.iso_standard_id:
            iso = await session.get(IsoStandard, device_cat.iso_standard_id)
            if iso:
                config["iso"] = {
                    "standard": iso.version,
                    "category": iso.category,
                    "foundation": iso.foundation,
                }

        # 5. HealthCheckFreq (patrol, diagnosis, report)
        if device_cat.health_check_freq_id:
            hcf = await session.get(HealthCheckFreq, device_cat.health_check_freq_id)
            if hcf:
                config["patrol"] = hcf.patrol
                config["diagnosis"] = hcf.diagnosis
                config["report"] = hcf.report

        # 6. Tenant mqtt_server and api_server
        if device_cat.tenant_id:
            tenant = await session.get(Tenant, device_cat.tenant_id)
            if tenant:
                config["mqtt_host"] = tenant.mqtt_server or "mqtt.api-server.icu"
                config["api_host"] = tenant.api_server or "api.api-server.icu"

        # 7. SensorType values (battery, network)
        if sensor_type:
            config["voltage"] = sensor_type.battery
            config["network"] = sensor_type.network

        # 8. WiFi credentials via ProcessDeviceItem → ProcessDevice → Area
        stmt3 = (
            select(Area)
            .join(ProcessDevice, ProcessDevice.area_id == Area.id)
            .join(ProcessDeviceItem, ProcessDeviceItem.process_device_id == ProcessDevice.id)
            .where(ProcessDeviceItem.device_inst_id == device_inst.id)
            .limit(1)
        )
        result3 = await session.execute(stmt3)
        area = result3.scalar_one_or_none()
        if area:
            config["wifi"] = {
                "ssid": area.ssid or "",
                "pass": area.passwd or "",
            }

        # 9. configured = all critical links present
        config["configured"] = bool(
            iso and hcf and tenant and sensor_type
        )

        return config

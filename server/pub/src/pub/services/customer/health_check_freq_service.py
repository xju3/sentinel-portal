"""
Customer service - business logic for customer operations
"""

from uuid import UUID
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_

from pub.models.customer import (
    Region,
    Tenant,
    TenantSensor,
    Supplier,
    Contact,
    Account,
    Area,
    Location,
    HealthCheckFreq,
    IsoStandard,
)
from pub.exceptions.domain_exception import DomainException
from pub.utils.sorting import apply_sorting

from pub.models.sensor import SensorMonitoring, Sensor
from pub.models.device import DeviceCategory, DeviceSpec, DeviceInst

class HealthCheckFreqService:
    @staticmethod
    async def get_health_check_freqs(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        sort_by: str | None = None,
        sort_order: str = "ascend",
        keyword: Optional[str] = None,
        patrol: Optional[float] = None,
        diagnosis: Optional[float] = None,
        report: Optional[int] = None,
        status: Optional[bool] = None,
    ) -> tuple[List[HealthCheckFreq], int]:
        stmt = select(HealthCheckFreq).where(HealthCheckFreq.tenant_id == tenant_id)
        if keyword:
            value = keyword.strip()
            numeric_filters = []
            try:
                numeric = float(value)
                numeric_filters.extend(
                    [HealthCheckFreq.patrol == numeric, HealthCheckFreq.diagnosis == numeric]
                )
            except ValueError:
                pass
            if numeric_filters:
                stmt = stmt.where(or_(*numeric_filters))
        if status is not None:
            stmt = stmt.where(HealthCheckFreq.status == status)
        if patrol is not None:
            stmt = stmt.where(HealthCheckFreq.patrol == patrol)
        if diagnosis is not None:
            stmt = stmt.where(HealthCheckFreq.diagnosis == diagnosis)
        if report is not None:
            stmt = stmt.where(HealthCheckFreq.report == report)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0
        stmt = apply_sorting(stmt, HealthCheckFreq, sort_by, sort_order)
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all(), total

    @staticmethod
    async def get_health_check_by_sensor_sn(
        session: AsyncSession,
        sn: str,
    ) -> Optional[HealthCheckFreq]:
        
        stmt = (
            select(HealthCheckFreq)
            .join(DeviceCategory, DeviceCategory.health_check_freq_id == HealthCheckFreq.id)
            .join(DeviceSpec, DeviceSpec.device_category_id == DeviceCategory.id)
            .join(DeviceInst, DeviceInst.device_spec_id == DeviceSpec.id)
            .join(
                SensorMonitoring,
                (SensorMonitoring.device_inst_id == DeviceInst.id)
                & (SensorMonitoring.status == 1),
            )
            .join(Sensor, Sensor.id == SensorMonitoring.sensor_id)
            .where(Sensor.sn == sn)
        )
        
        result = await session.execute(stmt)
        # 同样使用第一问提到的 scalars().first() 或 scalar_one_or_none()
        return result.scalars().first()

    @staticmethod
    async def get_health_check_freq(
        session: AsyncSession,
        tenant_id: UUID,
        freq_id: UUID,
    ) -> Optional[HealthCheckFreq]:
        stmt = select(HealthCheckFreq).where(
            HealthCheckFreq.id == freq_id,
            HealthCheckFreq.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_health_check_freq(session: AsyncSession, data: dict) -> HealthCheckFreq:
        db_freq = HealthCheckFreq(**data)
        session.add(db_freq)
        await session.commit()
        await session.refresh(db_freq)
        return db_freq

    @staticmethod
    async def update_health_check_freq(
        session: AsyncSession,
        db_freq: HealthCheckFreq,
        data: dict,
    ) -> HealthCheckFreq:
        for key, value in data.items():
            setattr(db_freq, key, value)
        await session.commit()
        await session.refresh(db_freq)
        return db_freq

    @staticmethod
    async def delete_health_check_freq(session: AsyncSession, db_freq: HealthCheckFreq) -> None:
        await session.delete(db_freq)
        await session.commit()

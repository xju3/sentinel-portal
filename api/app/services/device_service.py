"""
Device service - business logic for device operations
"""

from uuid import UUID
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_

from app.models.device import (
    IsoStandard,
    DeviceCategory,
    DeviceSpec,
    DeviceInst,
    Process,
    ProcessItem,
    ProcessDevice,
    ProcessDeviceItem,
    SensorMonitoring,
)
from app.models.customer import HealthCheckFreq


class IsoStandardService:
    @staticmethod
    async def get_all(session: AsyncSession, skip: int, limit: int) -> List[IsoStandard]:
        stmt = select(IsoStandard).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_by_id(session: AsyncSession, obj_id: UUID) -> Optional[IsoStandard]:
        stmt = select(IsoStandard).where(IsoStandard.id == obj_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> IsoStandard:
        db_obj = IsoStandard(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(session: AsyncSession, db_obj: IsoStandard, data: dict) -> IsoStandard:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: IsoStandard) -> None:
        await session.delete(db_obj)
        await session.commit()


class DeviceCategoryService:
    @staticmethod
    async def get_all(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int,
        limit: int,
        keyword: Optional[str] = None,
    ) -> List[DeviceCategory]:
        stmt = select(DeviceCategory).where(DeviceCategory.tenant_id == tenant_id)
        if keyword:
            like_kw = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    DeviceCategory.name.ilike(like_kw),
                    DeviceCategory.description.ilike(like_kw),
                )
            )
        stmt = stmt.offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def count_all(
        session: AsyncSession,
        tenant_id: UUID,
        keyword: Optional[str] = None,
    ) -> int:
        stmt = select(func.count(DeviceCategory.id)).where(DeviceCategory.tenant_id == tenant_id)
        if keyword:
            like_kw = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    DeviceCategory.name.ilike(like_kw),
                    DeviceCategory.description.ilike(like_kw),
                )
            )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def has_children(session: AsyncSession, tenant_id: UUID, obj_id: UUID) -> bool:
        stmt = (
            select(DeviceCategory.id)
            .where(
                DeviceCategory.parent_id == obj_id,
                DeviceCategory.tenant_id == tenant_id,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        tenant_id: UUID,
        obj_id: UUID,
    ) -> Optional[DeviceCategory]:
        stmt = select(DeviceCategory).where(
            DeviceCategory.id == obj_id,
            DeviceCategory.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_health_check_freq_map(
        session: AsyncSession,
        tenant_id: UUID,
        freq_ids: List[UUID],
    ) -> dict[UUID, HealthCheckFreq]:
        if not freq_ids:
            return {}
        stmt = select(HealthCheckFreq).where(
            HealthCheckFreq.tenant_id == tenant_id,
            HealthCheckFreq.id.in_(freq_ids),
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return {row.id: row for row in rows}

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> DeviceCategory:
        db_obj = DeviceCategory(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(session: AsyncSession, db_obj: DeviceCategory, data: dict) -> DeviceCategory:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: DeviceCategory) -> None:
        await session.delete(db_obj)
        await session.commit()


class DeviceSpecService:
    @staticmethod
    async def get_all(session: AsyncSession, skip: int, limit: int) -> List[DeviceSpec]:
        stmt = select(DeviceSpec).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_by_id(session: AsyncSession, obj_id: UUID) -> Optional[DeviceSpec]:
        stmt = select(DeviceSpec).where(DeviceSpec.id == obj_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> DeviceSpec:
        db_obj = DeviceSpec(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(session: AsyncSession, db_obj: DeviceSpec, data: dict) -> DeviceSpec:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: DeviceSpec) -> None:
        await session.delete(db_obj)
        await session.commit()


class DeviceInstService:
    @staticmethod
    async def get_all(session: AsyncSession, skip: int, limit: int) -> List[DeviceInst]:
        stmt = select(DeviceInst).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_by_id(session: AsyncSession, obj_id: UUID) -> Optional[DeviceInst]:
        stmt = select(DeviceInst).where(DeviceInst.id == obj_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> DeviceInst:
        db_obj = DeviceInst(**data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def update(session: AsyncSession, db_obj: DeviceInst, data: dict) -> DeviceInst:
        for key, value in data.items():
            setattr(db_obj, key, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: DeviceInst) -> None:
        await session.delete(db_obj)
        await session.commit()


def generate_standard_service(model_class):
    """Factory class to generate basic CRUD services to avoid excessive boilerplate"""
    class StandardService:
        @staticmethod
        async def get_all(session: AsyncSession, skip: int, limit: int):
            stmt = select(model_class).offset(skip).limit(limit)
            result = await session.execute(stmt)
            return result.scalars().all()

        @staticmethod
        async def get_by_id(session: AsyncSession, obj_id: UUID):
            stmt = select(model_class).where(model_class.id == obj_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

        @staticmethod
        async def create(session: AsyncSession, data: dict):
            db_obj = model_class(**data)
            session.add(db_obj)
            await session.commit()
            await session.refresh(db_obj)
            return db_obj

        @staticmethod
        async def update(session: AsyncSession, db_obj, data: dict):
            for key, value in data.items():
                setattr(db_obj, key, value)
            await session.commit()
            await session.refresh(db_obj)
            return db_obj

        @staticmethod
        async def delete(session: AsyncSession, db_obj) -> None:
            await session.delete(db_obj)
            await session.commit()

    return StandardService


# 使用工厂模式来创建剩余的模型 Service 以减少代码冗余
# 如果这些模型后续需要扩展复杂的特定业务逻辑，可以随时像上面那样独立定义类

ProcessService = generate_standard_service(Process)
ProcessItemService = generate_standard_service(ProcessItem)
ProcessDeviceService = generate_standard_service(ProcessDevice)
ProcessDeviceItemService = generate_standard_service(ProcessDeviceItem)
SensorMonitoringService = generate_standard_service(SensorMonitoring)

# Backward-compatible aliases for legacy router names.
DeviceComboSpecService = ProcessService
DeviceComboSpecItemService = ProcessItemService
DeviceComboInstService = ProcessDeviceService
DeviceComboInstItemService = ProcessDeviceItemService
DeviceInstTagService = SensorMonitoringService

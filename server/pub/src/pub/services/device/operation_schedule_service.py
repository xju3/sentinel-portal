"""Tenant-scoped device operation schedule and item operations."""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pub.models.device import (
    DeviceOperationSchedule,
    DeviceOperationScheduleItem,
    DeviceSpec,
)
from pub.services.device.bearing_service import BearingService

logger = logging.getLogger(__name__)


class OperationScheduleConflictError(ValueError):
    """A concurrent or persisted reference conflicts with the requested write."""


class DeviceOperationScheduleService:
    ConflictError = OperationScheduleConflictError

    @staticmethod
    async def list_schedules(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 20,
        sort_by: str | None = None,
        sort_order: str = "ascend",
        keyword: str | None = None,
        code: str | None = None,
        name: str | None = None,
        description: str | None = None,
        status: int | None = None,
    ) -> tuple[list[DeviceOperationSchedule], int]:
        stmt = select(DeviceOperationSchedule).where(
            DeviceOperationSchedule.tenant_id == tenant_id
        )
        if keyword:
            like = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    DeviceOperationSchedule.code.ilike(like),
                    DeviceOperationSchedule.name.ilike(like),
                    DeviceOperationSchedule.description.ilike(like),
                )
            )
        if code:
            stmt = stmt.where(
                DeviceOperationSchedule.code.ilike(f"%{code.strip()}%")
            )
        if name:
            stmt = stmt.where(
                DeviceOperationSchedule.name.ilike(f"%{name.strip()}%")
            )
        if description:
            stmt = stmt.where(
                DeviceOperationSchedule.description.ilike(
                    f"%{description.strip()}%"
                )
            )
        if status is not None:
            stmt = stmt.where(DeviceOperationSchedule.status == status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        order_column = (
            getattr(DeviceOperationSchedule, sort_by, None) if sort_by else None
        )
        if order_column is None:
            stmt = stmt.order_by(
                DeviceOperationSchedule.code.asc(),
                DeviceOperationSchedule.name.asc(),
            )
        elif sort_order == "descend":
            stmt = stmt.order_by(order_column.desc())
        else:
            stmt = stmt.order_by(order_column.asc())

        stmt = (
            stmt.options(selectinload(DeviceOperationSchedule.items))
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        tenant_id: UUID,
        schedule_id: UUID,
    ) -> DeviceOperationSchedule | None:
        result = await session.execute(
            select(DeviceOperationSchedule)
            .options(selectinload(DeviceOperationSchedule.items))
            .where(
                DeviceOperationSchedule.id == schedule_id,
                DeviceOperationSchedule.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def find_duplicate(
        session: AsyncSession,
        tenant_id: UUID,
        code: str,
        exclude_id: UUID | None = None,
    ) -> DeviceOperationSchedule | None:
        stmt = select(DeviceOperationSchedule).where(
            DeviceOperationSchedule.tenant_id == tenant_id,
            func.lower(DeviceOperationSchedule.code) == code.casefold(),
        )
        if exclude_id is not None:
            stmt = stmt.where(DeviceOperationSchedule.id != exclude_id)
        result = await session.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        tenant_id: UUID,
        data: dict[str, Any],
    ) -> DeviceOperationSchedule:
        obj = DeviceOperationSchedule(tenant_id=tenant_id, **data)
        session.add(obj)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise ValueError("运行模式编码已存在") from exc
        await session.refresh(obj)
        await session.refresh(obj, attribute_names=["items"])
        return obj

    @staticmethod
    async def update(
        session: AsyncSession,
        obj: DeviceOperationSchedule,
        data: dict[str, Any],
    ) -> DeviceOperationSchedule:
        for key, value in data.items():
            setattr(obj, key, value)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise ValueError("运行模式编码已存在") from exc
        await session.refresh(obj)
        await session.refresh(obj, attribute_names=["items"])
        affected_specs = await DeviceOperationScheduleService._spec_ids_for_schedule(
            session, obj.id
        )
        if affected_specs:
            await BearingService.invalidate_diagnosis_cache(session, affected_specs)
        return obj

    @staticmethod
    async def delete(
        session: AsyncSession,
        obj: DeviceOperationSchedule,
    ) -> None:
        bound = await session.execute(
            select(DeviceSpec.id)
            .where(DeviceSpec.reference_id == obj.id)
            .limit(1)
        )
        if bound.scalar_one_or_none() is not None:
            raise ValueError("该运行模式已被设备规格关联，无法删除")
        await session.delete(obj)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise OperationScheduleConflictError(
                "该运行模式已被设备规格关联，无法删除"
            ) from exc

    @staticmethod
    async def list_items(
        session: AsyncSession,
        tenant_id: UUID,
        schedule_id: UUID,
    ) -> list[DeviceOperationScheduleItem] | None:
        schedule = await DeviceOperationScheduleService.get_by_id(
            session, tenant_id, schedule_id
        )
        if schedule is None:
            return None
        result = await session.execute(
            select(DeviceOperationScheduleItem)
            .where(DeviceOperationScheduleItem.schedule_id == schedule_id)
            .order_by(
                DeviceOperationScheduleItem.seq.asc(),
                DeviceOperationScheduleItem.id.asc(),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def replace_items(
        session: AsyncSession,
        tenant_id: UUID,
        schedule_id: UUID,
        items: list[dict[str, Any]],
    ) -> list[DeviceOperationScheduleItem] | None:
        schedule = await DeviceOperationScheduleService.get_by_id(
            session, tenant_id, schedule_id
        )
        if schedule is None:
            return None

        await session.execute(
            delete(DeviceOperationScheduleItem).where(
                DeviceOperationScheduleItem.schedule_id == schedule_id
            )
        )
        new_rows = [
            DeviceOperationScheduleItem(
                schedule_id=schedule_id,
                cron_expr=str(item["cron_expr"]).strip(),
                duration_minutes=int(item["duration_minutes"]),
                remark=item.get("remark"),
                seq=int(item.get("seq", idx)),
            )
            for idx, item in enumerate(items)
        ]
        session.add_all(new_rows)
        await session.commit()

        affected_specs = await DeviceOperationScheduleService._spec_ids_for_schedule(
            session, schedule_id
        )
        if affected_specs:
            await BearingService.invalidate_diagnosis_cache(session, affected_specs)
            from pub.services.config.config_service import (
                create_config_tasks,
                find_affected_sns,
            )

            sns = await find_affected_sns(
                session, DeviceOperationSchedule, schedule_id
            )
            if sns:
                await create_config_tasks(session, sns)

        return await DeviceOperationScheduleService.list_items(
            session, tenant_id, schedule_id
        )

    @staticmethod
    async def _spec_ids_for_schedule(
        session: AsyncSession,
        schedule_id: UUID,
    ) -> list[UUID]:
        result = await session.execute(
            select(DeviceSpec.id).where(DeviceSpec.reference_id == schedule_id)
        )
        return list(set(result.scalars().all()))

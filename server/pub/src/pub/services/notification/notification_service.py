from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pub.models.customer import Area, Location
from pub.models.device import (
    DeviceCategory,
    DeviceCategoryEmployee,
    DeviceInst,
    DeviceSpec,
    Process,
    ProcessDevice,
    ProcessDeviceEmployee,
    ProcessDeviceItem,
)
from pub.models.diagnosis import (
    Diagnosis,
    DiagnosisItem,
    DiagnosisNotificationDelivery,
    DiagnosisNotificationDeliveryStatus,
    DiagnosisRecord,
)
from pub.models.org import Employee
from pub.models.sensor import Sensor, SensorMonitoring

logger = logging.getLogger(__name__)

BEIJING_TZ = ZoneInfo("Asia/Shanghai")
LEVEL_LABELS = {
    0: "正常",
    1: "关注",
    2: "异常",
    3: "告警",
    4: "严重",
}
RouteSource = Literal["device_category", "process_device"]


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DiagnosisNotificationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    diagnosis_id: UUID
    report_id: UUID | None = None
    device_id: UUID
    sensor_sn: str
    overall_level: int = Field(..., ge=1, le=4)
    device_category_id: UUID | None = None
    process_device_id: UUID | None = None
    diagnosed_at: datetime

    @field_validator("sensor_sn")
    @classmethod
    def _validate_sensor_sn(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("sensor_sn must not be empty")
        return value

    @field_validator("diagnosed_at", mode="after")
    @classmethod
    def _normalize_diagnosed_at(cls, value: datetime) -> datetime:
        return _ensure_utc(value)

    @property
    def notification_date(self) -> date:
        return self.diagnosed_at.astimezone(BEIJING_TZ).date()


class NotificationRouteResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_category_id: UUID | None = None
    process_device_id: UUID | None = None
    device_category_source: Literal[
        "device", "event", "sensor_sn", "ambiguous", "missing"
    ] = "missing"
    process_device_source: Literal[
        "device", "event", "sensor_sn", "ambiguous", "missing"
    ] = "missing"


class NotificationRecipient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: UUID
    employee_name: str | None = None
    wx_user_id: str
    route_sources: tuple[RouteSource, ...]

    @field_validator("wx_user_id")
    @classmethod
    def _validate_wx_user_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("wx_user_id must not be empty")
        return value


class NotificationDispatchTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivery_id: UUID
    employee_id: UUID
    employee_name: str | None = None
    wx_user_id: str
    status: DiagnosisNotificationDeliveryStatus
    should_send: bool
    skip_reason: str | None = None
    route_sources: tuple[RouteSource, ...]


class NotificationMessageContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivery_id: UUID
    event_id: UUID
    diagnosis_id: UUID
    report_id: UUID | None = None
    device_id: UUID
    sensor_sn: str | None = None
    overall_level: int
    overall_level_label: str
    diagnosed_at: datetime
    notification_date: date
    device_name: str | None = None
    device_code: str | None = None
    location_name: str | None = None
    device_category_id: UUID | None = None
    device_category_name: str | None = None
    process_device_id: UUID | None = None
    process_code: str | None = None
    process_name: str | None = None
    area_name: str | None = None
    diagnosis_items: list[str] = Field(default_factory=list)


class NotificationService:
    @staticmethod
    def parse_event(payload: dict[str, Any] | str | bytes) -> DiagnosisNotificationEvent:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            raise ValueError("Diagnosis notification payload must be a JSON object")
        return DiagnosisNotificationEvent.model_validate(payload)

    @staticmethod
    async def resolve_route_ids(
        session: AsyncSession,
        event: DiagnosisNotificationEvent,
    ) -> NotificationRouteResolution:
        device_route = await NotificationService._route_ids_by_device_id(
            session,
            event.device_id,
        )

        device_category_ambiguous = bool(device_route["device_category_ambiguous"])
        process_device_ambiguous = bool(device_route["process_device_ambiguous"])
        device_category_id = (
            None
            if device_category_ambiguous
            else device_route["device_category_id"] or event.device_category_id
        )
        process_device_id = (
            None
            if process_device_ambiguous
            else device_route["process_device_id"] or event.process_device_id
        )
        device_category_source = (
            "ambiguous"
            if device_category_ambiguous
            else "device"
            if device_route["device_category_id"]
            else "event"
            if event.device_category_id
            else "missing"
        )
        process_device_source = (
            "ambiguous"
            if process_device_ambiguous
            else "device"
            if device_route["process_device_id"]
            else "event"
            if event.process_device_id
            else "missing"
        )

        if event.sensor_sn and (
            (device_category_id is None and not device_category_ambiguous)
            or (process_device_id is None and not process_device_ambiguous)
        ):
            sensor_route = await NotificationService._route_ids_by_sensor_sn(
                session,
                event.sensor_sn,
            )
            if sensor_route["device_category_ambiguous"]:
                device_category_id = None
                device_category_source = "ambiguous"
            elif (
                device_category_id is None
                and sensor_route["device_category_id"] is not None
            ):
                device_category_id = sensor_route["device_category_id"]
                device_category_source = "sensor_sn"
            if sensor_route["process_device_ambiguous"]:
                process_device_id = None
                process_device_source = "ambiguous"
            elif (
                process_device_id is None
                and sensor_route["process_device_id"] is not None
            ):
                process_device_id = sensor_route["process_device_id"]
                process_device_source = "sensor_sn"

        return NotificationRouteResolution(
            device_category_id=device_category_id,
            process_device_id=process_device_id,
            device_category_source=device_category_source,
            process_device_source=process_device_source,
        )

    @staticmethod
    async def list_recipients(
        session: AsyncSession,
        event: DiagnosisNotificationEvent,
    ) -> list[NotificationRecipient]:
        route = await NotificationService.resolve_route_ids(session, event)
        recipients: dict[UUID, NotificationRecipient] = {}

        if route.device_category_id:
            category_rows = await NotificationService._recipient_rows_for_device_category(
                session,
                route.device_category_id,
            )
            NotificationService._merge_recipient_rows(
                recipients,
                category_rows,
                "device_category",
            )

        if route.process_device_id:
            process_rows = await NotificationService._recipient_rows_for_process_device(
                session,
                route.process_device_id,
            )
            NotificationService._merge_recipient_rows(
                recipients,
                process_rows,
                "process_device",
            )

        return list(recipients.values())

    @staticmethod
    async def prepare_delivery_targets(
        session: AsyncSession,
        event: DiagnosisNotificationEvent,
    ) -> list[NotificationDispatchTarget]:
        route = await NotificationService.resolve_route_ids(session, event)
        recipients = await NotificationService.list_recipients(session, event)
        if not recipients:
            return []

        notification_date = event.notification_date
        insert_rows = [
            {
                "event_id": event.event_id,
                "diagnosis_id": event.diagnosis_id,
                "report_id": event.report_id,
                "device_id": event.device_id,
                "sensor_sn": event.sensor_sn,
                "device_category_id": route.device_category_id,
                "process_device_id": route.process_device_id,
                "overall_level": event.overall_level,
                "employee_id": recipient.employee_id,
                "wx_user_id": recipient.wx_user_id,
                "notification_date": notification_date,
                "diagnosed_at": event.diagnosed_at.replace(tzinfo=None),
                "status": int(DiagnosisNotificationDeliveryStatus.PENDING),
            }
            for recipient in recipients
        ]
        await session.execute(
            mysql_insert(DiagnosisNotificationDelivery)
            .values(insert_rows)
            .prefix_with("IGNORE")
        )
        await session.commit()

        delivery_rows = (
            await session.execute(
                select(DiagnosisNotificationDelivery).where(
                    DiagnosisNotificationDelivery.device_id == event.device_id,
                    DiagnosisNotificationDelivery.overall_level == event.overall_level,
                    DiagnosisNotificationDelivery.notification_date == notification_date,
                    DiagnosisNotificationDelivery.employee_id.in_(
                        [recipient.employee_id for recipient in recipients]
                    ),
                )
            )
        ).scalars().all()
        deliveries = {row.employee_id: row for row in delivery_rows}

        targets: list[NotificationDispatchTarget] = []
        for recipient in recipients:
            delivery = deliveries.get(recipient.employee_id)
            if delivery is None:
                continue
            status = DiagnosisNotificationDeliveryStatus(int(delivery.status))
            should_send = status == DiagnosisNotificationDeliveryStatus.PENDING
            skip_reason = None if should_send else status.name.lower()
            targets.append(
                NotificationDispatchTarget(
                    delivery_id=delivery.id,
                    employee_id=recipient.employee_id,
                    employee_name=recipient.employee_name,
                    wx_user_id=delivery.wx_user_id,
                    status=status,
                    should_send=should_send,
                    skip_reason=skip_reason,
                    route_sources=recipient.route_sources,
                )
            )
        return targets

    @staticmethod
    async def mark_delivery_sending(
        session: AsyncSession,
        delivery_id: UUID,
    ) -> bool:
        result = await session.execute(
            update(DiagnosisNotificationDelivery)
            .where(
                DiagnosisNotificationDelivery.id == delivery_id,
                DiagnosisNotificationDelivery.status
                == int(DiagnosisNotificationDeliveryStatus.PENDING),
            )
            .values(
                status=int(DiagnosisNotificationDeliveryStatus.SENDING),
                updated_at=_utc_naive_now(),
            )
        )
        await session.commit()
        return bool(result.rowcount)

    @staticmethod
    async def mark_delivery_sent(
        session: AsyncSession,
        delivery_id: UUID,
    ) -> bool:
        result = await session.execute(
            update(DiagnosisNotificationDelivery)
            .where(
                DiagnosisNotificationDelivery.id == delivery_id,
                DiagnosisNotificationDelivery.status
                == int(DiagnosisNotificationDeliveryStatus.SENDING),
            )
            .values(
                status=int(DiagnosisNotificationDeliveryStatus.SENT),
                sent_at=_utc_naive_now(),
                last_error=None,
                updated_at=_utc_naive_now(),
            )
        )
        await session.commit()
        return bool(result.rowcount)

    @staticmethod
    async def mark_delivery_failed(
        session: AsyncSession,
        delivery_id: UUID,
        error: str,
    ) -> bool:
        result = await session.execute(
            update(DiagnosisNotificationDelivery)
            .where(
                DiagnosisNotificationDelivery.id == delivery_id,
                DiagnosisNotificationDelivery.status
                == int(DiagnosisNotificationDeliveryStatus.SENDING),
            )
            .values(
                status=int(DiagnosisNotificationDeliveryStatus.FAILED),
                last_error=(error or "")[:1024] or None,
                updated_at=_utc_naive_now(),
            )
        )
        await session.commit()
        return bool(result.rowcount)

    @staticmethod
    async def get_message_context(
        session: AsyncSession,
        delivery_id: UUID,
    ) -> NotificationMessageContext | None:
        delivery = await session.get(DiagnosisNotificationDelivery, delivery_id)
        if delivery is None:
            return None

        diagnosed_at = _ensure_utc(delivery.diagnosed_at)
        sensor_sn = await NotificationService._sensor_sn_for_delivery(session, delivery)
        event = DiagnosisNotificationEvent(
            event_id=delivery.event_id,
            diagnosis_id=delivery.diagnosis_id,
            report_id=delivery.report_id,
            device_id=delivery.device_id,
            sensor_sn=sensor_sn,
            overall_level=int(delivery.overall_level),
            device_category_id=delivery.device_category_id,
            process_device_id=delivery.process_device_id,
            diagnosed_at=diagnosed_at,
        )
        route = await NotificationService.resolve_route_ids(session, event)

        device_row = (
            await session.execute(
                select(DeviceInst.name, DeviceInst.code).where(
                    DeviceInst.id == delivery.device_id
                )
            )
        ).one_or_none()
        location_name = await NotificationService._location_name_for_delivery(
            session,
            delivery,
        )
        device_category_name = await NotificationService._device_category_name(
            session,
            route.device_category_id,
        )
        process_context = await NotificationService._process_context(
            session,
            route.process_device_id,
        )
        diagnosis_items = await NotificationService._diagnosis_item_descriptions(
            session,
            delivery.diagnosis_id,
        )

        return NotificationMessageContext(
            delivery_id=delivery.id,
            event_id=delivery.event_id,
            diagnosis_id=delivery.diagnosis_id,
            report_id=delivery.report_id,
            device_id=delivery.device_id,
            sensor_sn=sensor_sn,
            overall_level=int(delivery.overall_level),
            overall_level_label=LEVEL_LABELS.get(int(delivery.overall_level), "未知"),
            diagnosed_at=diagnosed_at,
            notification_date=delivery.notification_date,
            device_name=device_row.name if device_row else None,
            device_code=device_row.code if device_row else None,
            location_name=location_name,
            device_category_id=route.device_category_id,
            device_category_name=device_category_name,
            process_device_id=route.process_device_id,
            process_code=process_context["process_code"],
            process_name=process_context["process_name"],
            area_name=process_context["area_name"],
            diagnosis_items=diagnosis_items,
        )

    @staticmethod
    async def _route_ids_by_device_id(
        session: AsyncSession,
        device_id: UUID,
    ) -> dict[str, UUID | bool | None]:
        rows = (
            await session.execute(
                select(
                    DeviceSpec.device_category_id,
                    ProcessDeviceItem.process_device_id,
                )
                .select_from(DeviceInst)
                .outerjoin(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
                .outerjoin(
                    ProcessDeviceItem,
                    ProcessDeviceItem.device_inst_id == DeviceInst.id,
                )
                .where(DeviceInst.id == device_id)
            )
        ).all()
        return NotificationService._coalesce_route_ids(
            rows,
            f"device_id={device_id}",
        )

    @staticmethod
    async def _route_ids_by_sensor_sn(
        session: AsyncSession,
        sensor_sn: str,
    ) -> dict[str, UUID | bool | None]:
        rows = (
            await session.execute(
                select(
                    DeviceSpec.device_category_id,
                    ProcessDeviceItem.process_device_id,
                )
                .select_from(Sensor)
                .join(SensorMonitoring, SensorMonitoring.sensor_id == Sensor.id)
                .outerjoin(DeviceInst, SensorMonitoring.device_inst_id == DeviceInst.id)
                .outerjoin(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
                .outerjoin(
                    ProcessDeviceItem,
                    ProcessDeviceItem.device_inst_id == DeviceInst.id,
                )
                .where(
                    Sensor.sn == sensor_sn,
                    SensorMonitoring.status == 1,
                )
            )
        ).all()
        return NotificationService._coalesce_route_ids(
            rows,
            f"sensor_sn={sensor_sn}",
        )

    @staticmethod
    def _coalesce_route_ids(
        rows: list[Any],
        relation_key: str,
    ) -> dict[str, UUID | bool | None]:
        device_category_ids = {
            row.device_category_id for row in rows if row.device_category_id is not None
        }
        process_device_ids = {
            row.process_device_id for row in rows if row.process_device_id is not None
        }
        device_category_id = None
        process_device_id = None

        if len(device_category_ids) == 1:
            device_category_id = next(iter(device_category_ids))
        elif len(device_category_ids) > 1:
            logger.error(
                "Multiple device_category_id values found for %s: %s",
                relation_key,
                sorted(str(value) for value in device_category_ids),
            )

        if len(process_device_ids) == 1:
            process_device_id = next(iter(process_device_ids))
        elif len(process_device_ids) > 1:
            logger.error(
                "Multiple process_device_id values found for %s: %s",
                relation_key,
                sorted(str(value) for value in process_device_ids),
            )

        return {
            "device_category_id": device_category_id,
            "process_device_id": process_device_id,
            "device_category_ambiguous": len(device_category_ids) > 1,
            "process_device_ambiguous": len(process_device_ids) > 1,
        }

    @staticmethod
    async def _recipient_rows_for_device_category(
        session: AsyncSession,
        device_category_id: UUID,
    ) -> list[Any]:
        return (
            await session.execute(
                select(Employee.id, Employee.name, Employee.wx_user_id)
                .join(
                    DeviceCategoryEmployee,
                    DeviceCategoryEmployee.employee_id == Employee.id,
                )
                .where(
                    DeviceCategoryEmployee.device_category_id == device_category_id,
                    DeviceCategoryEmployee.status.is_(True),
                    Employee.active.is_(True),
                    Employee.wx_user_id.is_not(None),
                    func.length(func.trim(Employee.wx_user_id)) > 0,
                )
            )
        ).all()

    @staticmethod
    async def _recipient_rows_for_process_device(
        session: AsyncSession,
        process_device_id: UUID,
    ) -> list[Any]:
        return (
            await session.execute(
                select(Employee.id, Employee.name, Employee.wx_user_id)
                .join(
                    ProcessDeviceEmployee,
                    ProcessDeviceEmployee.employee_id == Employee.id,
                )
                .where(
                    ProcessDeviceEmployee.process_device_id == process_device_id,
                    ProcessDeviceEmployee.status.is_(True),
                    Employee.active.is_(True),
                    Employee.wx_user_id.is_not(None),
                    func.length(func.trim(Employee.wx_user_id)) > 0,
                )
            )
        ).all()

    @staticmethod
    def _merge_recipient_rows(
        recipients: dict[UUID, NotificationRecipient],
        rows: list[Any],
        route_source: RouteSource,
    ) -> None:
        for row in rows:
            existing = recipients.get(row.id)
            if existing is None:
                recipients[row.id] = NotificationRecipient(
                    employee_id=row.id,
                    employee_name=row.name,
                    wx_user_id=row.wx_user_id,
                    route_sources=(route_source,),
                )
                continue

            route_sources = tuple(
                source
                for source in ("device_category", "process_device")
                if source in {*existing.route_sources, route_source}
            )
            recipients[row.id] = NotificationRecipient(
                employee_id=existing.employee_id,
                employee_name=existing.employee_name or row.name,
                wx_user_id=existing.wx_user_id,
                route_sources=route_sources,
            )

    @staticmethod
    async def _location_name_for_delivery(
        session: AsyncSession,
        delivery: DiagnosisNotificationDelivery,
    ) -> str | None:
        location_id = await session.scalar(
            select(Diagnosis.location_id).where(Diagnosis.id == delivery.diagnosis_id)
        )
        if location_id is None and delivery.report_id is not None:
            location_id = await session.scalar(
                select(DiagnosisRecord.location_id).where(
                    DiagnosisRecord.id == delivery.report_id
                )
            )
        if location_id is None:
            return None
        return await session.scalar(
            select(Location.name).where(Location.id == location_id)
        )

    @staticmethod
    async def _sensor_sn_for_delivery(
        session: AsyncSession,
        delivery: DiagnosisNotificationDelivery,
    ) -> str:
        if delivery.sensor_sn:
            return delivery.sensor_sn
        if delivery.report_id is not None:
            sensor_sn = await session.scalar(
                select(DiagnosisRecord.sensor_sn).where(
                    DiagnosisRecord.id == delivery.report_id
                )
            )
            if sensor_sn:
                return sensor_sn
        return str(delivery.device_id)

    @staticmethod
    async def _device_category_name(
        session: AsyncSession,
        device_category_id: UUID | None,
    ) -> str | None:
        if device_category_id is None:
            return None
        return await session.scalar(
            select(DeviceCategory.name).where(DeviceCategory.id == device_category_id)
        )

    @staticmethod
    async def _process_context(
        session: AsyncSession,
        process_device_id: UUID | None,
    ) -> dict[str, str | None]:
        if process_device_id is None:
            return {
                "process_code": None,
                "process_name": None,
                "area_name": None,
            }

        row = (
            await session.execute(
                select(
                    ProcessDevice.code.label("process_code"),
                    Process.name.label("process_name"),
                    Area.name.label("area_name"),
                )
                .select_from(ProcessDevice)
                .outerjoin(Process, ProcessDevice.process_id == Process.id)
                .outerjoin(Area, ProcessDevice.area_id == Area.id)
                .where(ProcessDevice.id == process_device_id)
            )
        ).one_or_none()
        if row is None:
            return {
                "process_code": None,
                "process_name": None,
                "area_name": None,
            }
        return {
            "process_code": row.process_code,
            "process_name": row.process_name,
            "area_name": row.area_name,
        }

    @staticmethod
    async def _diagnosis_item_descriptions(
        session: AsyncSession,
        diagnosis_id: UUID,
    ) -> list[str]:
        rows = (
            await session.execute(
                select(DiagnosisItem.description)
                .where(DiagnosisItem.diagnosis_id == diagnosis_id)
                .order_by(DiagnosisItem.metric_id.asc(), DiagnosisItem.id.asc())
            )
        ).scalars().all()
        descriptions: list[str] = []
        for description in rows:
            if description and description not in descriptions:
                descriptions.append(description)
        return descriptions

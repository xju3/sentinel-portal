from datetime import date, datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from pub.models.diagnosis import DiagnosisNotificationDeliveryStatus
from pub.services.notification import (
    DiagnosisNotificationEvent,
    DiagnosisNotificationFaultEvent,
    NotificationDispatchTarget,
    NotificationMessageContext,
    NotificationService,
)

from app.config import Settings
from app.services.notification_service import LocalNotificationService


class FakeSessionContext:
    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def session_factory():
    return FakeSessionContext()


def build_fault_event(
    *,
    fault_type: str = "legacy_aggregate",
    fault_level: int = 3,
) -> DiagnosisNotificationFaultEvent:
    return DiagnosisNotificationFaultEvent(
        source_schema_version=1 if fault_type == "legacy_aggregate" else 2,
        event_id=uuid4(),
        diagnosis_id=uuid4(),
        report_id=uuid4(),
        device_id=uuid4(),
        sensor_sn="SN-001",
        fault_type=fault_type,
        fault_level=fault_level,
        overall_level=fault_level if fault_type == "legacy_aggregate" else None,
        diagnosed_at=datetime(2026, 7, 29, 10, 30, tzinfo=timezone.utc),
    )


def build_target() -> NotificationDispatchTarget:
    return NotificationDispatchTarget(
        delivery_id=uuid4(),
        employee_id=uuid4(),
        employee_name="测试员工",
        wx_user_id="wx-user-001",
        status=DiagnosisNotificationDeliveryStatus.PENDING,
        should_send=True,
        route_sources=("device_category", "process_device"),
    )


def build_context(
    event: DiagnosisNotificationFaultEvent,
    target: NotificationDispatchTarget,
) -> NotificationMessageContext:
    return NotificationMessageContext(
        delivery_id=target.delivery_id,
        event_id=event.event_id,
        diagnosis_id=event.diagnosis_id,
        report_id=event.report_id,
        device_id=event.device_id,
        sensor_sn=event.sensor_sn,
        diagnosis_item_id=event.diagnosis_item_id,
        fault_type=event.fault_type,
        fault_label="振动" if event.fault_type == "vibration" else "综合",
        fault_level=event.fault_level,
        fault_level_label="告警",
        overall_level=event.overall_level,
        overall_level_label="告警" if event.overall_level else None,
        diagnosed_at=event.diagnosed_at,
        notification_date=date(2026, 7, 29),
        device_name="循环泵",
        device_code="PUMP-001",
        diagnosis_items=["振动超限"],
    )


def test_local_service_exposes_shared_event_parser():
    fault_event = build_fault_event()
    parsed = LocalNotificationService.parse_event(
        json.dumps(
            {
                "event_id": str(fault_event.event_id),
                "diagnosis_id": str(fault_event.diagnosis_id),
                "report_id": str(fault_event.report_id),
                "device_id": str(fault_event.device_id),
                "sensor_sn": fault_event.sensor_sn,
                "overall_level": fault_event.fault_level,
                "diagnosed_at": fault_event.diagnosed_at.isoformat(),
            }
        )
    )

    assert parsed.schema_version == 1
    assert len(parsed.expanded_faults()) == 1
    assert parsed.expanded_faults()[0] == fault_event


def test_local_service_parse_event_expands_v2_faults():
    event_id = uuid4()
    diagnosis_id = uuid4()
    report_id = uuid4()
    device_id = uuid4()
    item_a = uuid4()
    item_b = uuid4()

    parsed = LocalNotificationService.parse_event(
        json.dumps(
            {
                "schema_version": 2,
                "event_id": str(event_id),
                "diagnosis_id": str(diagnosis_id),
                "report_id": str(report_id),
                "device_id": str(device_id),
                "sensor_sn": "SN-001",
                "diagnosed_at": "2026-07-29T10:30:00+00:00",
                "faults": [
                    {
                        "diagnosis_item_id": str(item_a),
                        "fault_type": "temperature",
                        "fault_level": 2,
                    },
                    {
                        "diagnosis_item_id": str(item_b),
                        "fault_type": "vibration",
                        "fault_level": 3,
                    },
                ],
            }
        )
    )

    fault_events = parsed.expanded_faults()
    assert parsed.schema_version == 2
    assert [event.fault_type for event in fault_events] == ["temperature", "vibration"]
    assert [event.fault_level for event in fault_events] == [2, 3]
    assert [event.diagnosis_item_id for event in fault_events] == [item_a, item_b]


@pytest.mark.asyncio
async def test_process_event_sends_and_marks_delivery_sent(monkeypatch):
    fault_event = build_fault_event(fault_type="vibration")
    event = DiagnosisNotificationEvent(schema_version=2, fault_events=(fault_event,))
    target = build_target()
    context = build_context(fault_event, target)
    wx_service = SimpleNamespace(send_template_message=AsyncMock(return_value=True))

    monkeypatch.setattr(
        NotificationService,
        "prepare_delivery_targets",
        AsyncMock(return_value=[target]),
    )
    monkeypatch.setattr(
        NotificationService,
        "mark_delivery_sending",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        NotificationService,
        "get_message_context",
        AsyncMock(return_value=context),
    )
    mark_sent = AsyncMock(return_value=True)
    monkeypatch.setattr(NotificationService, "mark_delivery_sent", mark_sent)

    service = LocalNotificationService(
        session_factory=session_factory,
        wx_service=wx_service,
        settings=Settings(),
    )
    result = await service.process_event(event)

    assert result == {
        "status": "processed",
        "sent": 1,
        "failed": 0,
        "skipped": 0,
    }
    wx_service.send_template_message.assert_awaited_once()
    assert (
        wx_service.send_template_message.await_args.kwargs["data"]["time3"]["value"]
        == "2026-07-29 18:30:00"
    )
    assert "delivery_id=" in wx_service.send_template_message.await_args.kwargs["url"]
    assert "report_id=" in wx_service.send_template_message.await_args.kwargs["url"]
    assert "fault_type=vibration" in wx_service.send_template_message.await_args.kwargs["url"]
    mark_sent.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_event_marks_wechat_failure_for_mqtt_redelivery(monkeypatch):
    fault_event = build_fault_event(fault_type="temperature")
    event = DiagnosisNotificationEvent(schema_version=2, fault_events=(fault_event,))
    target = build_target()
    context = build_context(fault_event, target)
    wx_service = SimpleNamespace(
        send_template_message=AsyncMock(side_effect=RuntimeError("wx unavailable"))
    )

    monkeypatch.setattr(
        NotificationService,
        "prepare_delivery_targets",
        AsyncMock(return_value=[target]),
    )
    monkeypatch.setattr(
        NotificationService,
        "mark_delivery_sending",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        NotificationService,
        "get_message_context",
        AsyncMock(return_value=context),
    )
    mark_failed = AsyncMock(return_value=True)
    monkeypatch.setattr(NotificationService, "mark_delivery_failed", mark_failed)

    service = LocalNotificationService(
        session_factory=session_factory,
        wx_service=wx_service,
        settings=Settings(),
    )
    with pytest.raises(
        RuntimeError,
        match="failed=1 deferred=0",
    ):
        await service.process_event(event)
    mark_failed.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_event_expands_multiple_faults(monkeypatch):
    fault_a = build_fault_event(fault_type="temperature", fault_level=2)
    fault_b = build_fault_event(fault_type="vibration", fault_level=3)
    event = DiagnosisNotificationEvent(schema_version=2, fault_events=(fault_a, fault_b))
    target_a = build_target()
    target_b = build_target()
    context_a = build_context(fault_a, target_a)
    context_b = build_context(fault_b, target_b)
    wx_service = SimpleNamespace(send_template_message=AsyncMock(return_value=True))

    monkeypatch.setattr(
        NotificationService,
        "prepare_delivery_targets",
        AsyncMock(side_effect=[[target_a], [target_b]]),
    )
    monkeypatch.setattr(
        NotificationService,
        "mark_delivery_sending",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        NotificationService,
        "get_message_context",
        AsyncMock(side_effect=[context_a, context_b]),
    )
    mark_sent = AsyncMock(return_value=True)
    monkeypatch.setattr(NotificationService, "mark_delivery_sent", mark_sent)

    service = LocalNotificationService(
        session_factory=session_factory,
        wx_service=wx_service,
        settings=Settings(),
    )
    result = await service.process_event(event)

    assert result == {
        "status": "processed",
        "sent": 2,
        "failed": 0,
        "skipped": 0,
    }
    assert NotificationService.prepare_delivery_targets.await_count == 2
    assert NotificationService.get_message_context.await_count == 2
    assert mark_sent.await_count == 2

from datetime import date, datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from pub.models.diagnosis import DiagnosisNotificationDeliveryStatus
from pub.services.notification import (
    DiagnosisNotificationEvent,
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


def build_event() -> DiagnosisNotificationEvent:
    return DiagnosisNotificationEvent(
        event_id=uuid4(),
        diagnosis_id=uuid4(),
        report_id=uuid4(),
        device_id=uuid4(),
        sensor_sn="SN-001",
        overall_level=3,
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
    event: DiagnosisNotificationEvent,
    target: NotificationDispatchTarget,
) -> NotificationMessageContext:
    return NotificationMessageContext(
        delivery_id=target.delivery_id,
        event_id=event.event_id,
        diagnosis_id=event.diagnosis_id,
        report_id=event.report_id,
        device_id=event.device_id,
        sensor_sn=event.sensor_sn,
        overall_level=event.overall_level,
        overall_level_label="告警",
        diagnosed_at=event.diagnosed_at,
        notification_date=date(2026, 7, 29),
        device_name="循环泵",
        device_code="PUMP-001",
        diagnosis_items=["振动超限"],
    )


def test_local_service_exposes_shared_event_parser():
    event = build_event()
    parsed = LocalNotificationService.parse_event(
        json.dumps(event.model_dump(mode="json"))
    )

    assert parsed == event


@pytest.mark.asyncio
async def test_process_event_sends_and_marks_delivery_sent(monkeypatch):
    event = build_event()
    target = build_target()
    context = build_context(event, target)
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
    mark_sent.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_event_marks_wechat_failure_and_finishes_event(monkeypatch):
    event = build_event()
    target = build_target()
    context = build_context(event, target)
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
    result = await service.process_event(event)

    assert result == {
        "status": "processed",
        "sent": 0,
        "failed": 1,
        "skipped": 0,
    }
    mark_failed.assert_awaited_once()

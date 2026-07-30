from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.clients.mqtt import IncomingMqttMessage
from app.config import Settings
from app.services.notification_service import LocalNotificationService
from app.services.worker import NotificationWorker


def build_payload() -> bytes:
    return (
        "{"
        f"\"event_id\":\"{uuid4()}\","
        f"\"diagnosis_id\":\"{uuid4()}\","
        f"\"report_id\":\"{uuid4()}\","
        f"\"device_id\":\"{uuid4()}\","
        "\"sensor_sn\":\"SN001\","
        "\"overall_level\":2,"
        f"\"diagnosed_at\":\"2026-07-29T10:30:00+00:00\""
        "}"
    ).encode()


@pytest.mark.asyncio
async def test_worker_acks_after_successful_processing():
    service = SimpleNamespace(
        parse_event=Mock(side_effect=LocalNotificationService.parse_event),
        process_event=AsyncMock(return_value={"status": "processed"}),
    )
    worker = NotificationWorker(service)
    client = Mock()
    client.ack.return_value = 0
    message = IncomingMqttMessage(
        topic="sentinel/notification/wechat",
        payload=build_payload(),
        qos=1,
        mid=7,
        client=client,
    )

    handled = await worker.handle_message(message)

    assert handled is True
    service.process_event.assert_awaited_once()
    client.ack.assert_called_once_with(7, 1)


@pytest.mark.asyncio
async def test_worker_acks_invalid_payload_to_unblock_queue():
    service = SimpleNamespace(
        parse_event=Mock(side_effect=LocalNotificationService.parse_event),
        process_event=AsyncMock(),
    )
    worker = NotificationWorker(service)
    client = Mock()
    client.ack.return_value = 0
    message = IncomingMqttMessage(
        topic="sentinel/notification/wechat",
        payload=b"{bad json",
        qos=1,
        mid=9,
        client=client,
    )

    handled = await worker.handle_message(message)

    assert handled is False
    service.process_event.assert_not_called()
    client.ack.assert_called_once_with(9, 1)


@pytest.mark.asyncio
async def test_worker_acks_invalid_utf8_with_real_parser():
    service = LocalNotificationService(
        session_factory=None,
        wx_service=None,
        settings=Settings(),
    )
    worker = NotificationWorker(service)
    client = Mock()
    client.ack.return_value = 0
    message = IncomingMqttMessage(
        topic="sentinel/notification/wechat",
        payload=b"\xff\xfe",
        qos=1,
        mid=10,
        client=client,
    )

    handled = await worker.handle_message(message)

    assert handled is False
    client.ack.assert_called_once_with(10, 1)


@pytest.mark.asyncio
async def test_worker_leaves_message_unacked_when_processing_raises():
    service = SimpleNamespace(
        parse_event=Mock(side_effect=LocalNotificationService.parse_event),
        process_event=AsyncMock(side_effect=RuntimeError("db down")),
    )
    worker = NotificationWorker(service)
    client = Mock()
    client.ack.return_value = 0
    message = IncomingMqttMessage(
        topic="sentinel/notification/wechat",
        payload=build_payload(),
        qos=1,
        mid=11,
        client=client,
    )

    handled = await worker.handle_message(message)

    assert handled is False
    client.ack.assert_not_called()

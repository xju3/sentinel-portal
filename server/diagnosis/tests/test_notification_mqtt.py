import json
from unittest.mock import Mock

import pytest

from app.clients import mqtt as diagnosis_mqtt
from pub.clients.mqtt import MQTTManager


def test_publish_confirmed_waits_for_broker_acknowledgement():
    manager = MQTTManager()
    publish_result = Mock()
    publish_result.rc = 0
    publish_result.is_published.return_value = True
    manager.client = Mock()
    manager.client.publish.return_value = publish_result

    assert manager.publish_confirmed(
        "sentinel/notification/wechat",
        "{}",
        qos=1,
        timeout=2.0,
    )

    manager.client.publish.assert_called_once_with(
        "sentinel/notification/wechat",
        "{}",
        qos=1,
    )
    publish_result.wait_for_publish.assert_called_once_with(timeout=2.0)


@pytest.mark.asyncio
async def test_publish_notification_event_uses_qos_one(monkeypatch):
    confirmed = Mock(return_value=True)
    monkeypatch.setattr(
        diagnosis_mqtt.diagnosis_mqtt_manager,
        "publish_confirmed",
        confirmed,
    )
    monkeypatch.setattr(
        diagnosis_mqtt.settings,
        "mqtt_notification_topic",
        "sentinel/notification/wechat",
    )
    monkeypatch.setattr(
        diagnosis_mqtt.settings,
        "mqtt_publish_timeout_seconds",
        3.0,
    )
    event = {
        "event_id": "event-1",
        "diagnosis_id": "diagnosis-1",
        "device_id": "device-1",
        "overall_level": 2,
    }

    assert await diagnosis_mqtt.publish_notification_event(event)

    topic, payload, qos, timeout = confirmed.call_args.args
    assert topic == "sentinel/notification/wechat"
    assert json.loads(payload) == event
    assert qos == 1
    assert timeout == 3.0


@pytest.mark.asyncio
async def test_publish_notification_event_failure_is_non_throwing(monkeypatch):
    monkeypatch.setattr(
        diagnosis_mqtt.diagnosis_mqtt_manager,
        "publish_confirmed",
        Mock(return_value=False),
    )

    assert not await diagnosis_mqtt.publish_notification_event(
        {
            "event_id": "event-1",
            "diagnosis_id": "diagnosis-1",
            "device_id": "device-1",
            "overall_level": 2,
        }
    )

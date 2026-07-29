import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.clients.mqtt import IncomingMqttMessage, NotificationMQTTClient
from app.config import Settings


class FakeClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.manual_ack_enabled = None
        self.subscriptions = []
        self.username = None
        self.password = None
        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None

    def username_pw_set(self, username, password):
        self.username = username
        self.password = password

    def manual_ack_set(self, enabled):
        self.manual_ack_enabled = enabled

    def subscribe(self, topic, qos):
        self.subscriptions.append((topic, qos))
        return (0, 1)


def build_settings() -> Settings:
    return Settings(
        mqtt_host="broker",
        mqtt_port=1883,
        mqtt_username="user",
        mqtt_password="pass",
        mqtt_notification_topic="sentinel/notification/wechat",
        mqtt_notification_client_id="sentinel-notification-client",
    )


def test_build_client_uses_persistent_session_and_manual_ack(monkeypatch):
    created: list[FakeClient] = []

    def fake_client_factory(*args, **kwargs):
        client = FakeClient(**kwargs)
        created.append(client)
        return client

    monkeypatch.setattr("app.clients.mqtt.mqtt.Client", fake_client_factory)
    monkeypatch.setattr("app.clients.mqtt.mqtt.MQTTv311", object())
    monkeypatch.setitem(__import__("sys").modules, "paho.mqtt.enums", None)

    mqtt_client = NotificationMQTTClient(build_settings(), worker=Mock())
    client = mqtt_client._build_client()

    assert client.kwargs["client_id"] == "sentinel-notification-client"
    assert client.kwargs["clean_session"] is False
    assert client.manual_ack_enabled is True
    assert client.username == "user"
    assert client.password == "pass"


def test_on_connect_resubscribes_with_qos_one():
    settings = build_settings()
    mqtt_client = NotificationMQTTClient(settings, worker=Mock())
    client = FakeClient()

    mqtt_client._on_connect(client, None, None, 0)

    assert client.subscriptions == [("sentinel/notification/wechat", 1)]


@pytest.mark.asyncio
async def test_on_message_schedules_message_into_asyncio_queue():
    mqtt_client = NotificationMQTTClient(build_settings(), worker=Mock())
    mqtt_client._loop = asyncio.get_running_loop()

    fake_message = SimpleNamespace(
        topic="sentinel/notification/wechat",
        payload=b'{"event_id":"x"}',
        qos=1,
        mid=12,
    )
    fake_client = FakeClient()

    mqtt_client._on_message(fake_client, None, fake_message)
    await asyncio.sleep(0)

    queued = await asyncio.wait_for(mqtt_client._queue.get(), timeout=1)
    assert isinstance(queued, IncomingMqttMessage)
    assert queued.client is fake_client
    assert queued.mid == 12
    assert queued.qos == 1
    assert queued.payload == b'{"event_id":"x"}'

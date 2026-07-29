import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import paho.mqtt.client as mqtt

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IncomingMqttMessage:
    topic: str
    payload: bytes
    qos: int
    mid: int
    client: mqtt.Client


class NotificationMQTTClient:
    def __init__(self, settings: Settings, worker: Any):
        self._settings = settings
        self._worker = worker
        self._client: mqtt.Client | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[IncomingMqttMessage] = asyncio.Queue()
        self._consumer_task: asyncio.Task[None] | None = None

    @property
    def client(self) -> mqtt.Client | None:
        return self._client

    async def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._client = self._build_client()
        self._consumer_task = asyncio.create_task(self._consume(), name="notification-mqtt-consumer")
        self._client.connect(
            self._settings.mqtt_host,
            self._settings.mqtt_port,
            keepalive=self._settings.mqtt_keepalive_seconds,
        )
        self._client.loop_start()
        logger.info(
            "Notification MQTT consumer started: topic=%s client_id=%s",
            self._settings.mqtt_notification_topic,
            self._settings.mqtt_notification_client_id,
        )

    async def stop(self) -> None:
        if self._consumer_task:
            self._consumer_task.cancel()
            await asyncio.gather(self._consumer_task, return_exceptions=True)
            self._consumer_task = None

        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None

    def _build_client(self) -> mqtt.Client:
        kwargs = {
            "client_id": self._settings.mqtt_notification_client_id,
            "protocol": mqtt.MQTTv311,
            "clean_session": False,
        }
        try:
            from paho.mqtt.enums import CallbackAPIVersion

            client = mqtt.Client(
                callback_api_version=CallbackAPIVersion.VERSION1,
                **kwargs,
            )
        except ImportError:
            client = mqtt.Client(**kwargs)

        if self._settings.mqtt_username and self._settings.mqtt_password:
            client.username_pw_set(
                self._settings.mqtt_username,
                self._settings.mqtt_password,
            )

        if hasattr(client, "manual_ack_set"):
            client.manual_ack_set(True)

        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        return client

    def _on_connect(self, client, userdata, flags, rc, *args) -> None:
        if rc != 0:
            logger.error("Notification MQTT connect failed: rc=%s", rc)
            return

        result, _mid = client.subscribe(
            self._settings.mqtt_notification_topic,
            qos=1,
        )
        if result == mqtt.MQTT_ERR_SUCCESS:
            logger.info(
                "Notification MQTT subscribed: topic=%s qos=1",
                self._settings.mqtt_notification_topic,
            )
        else:
            logger.error(
                "Notification MQTT subscribe failed: topic=%s rc=%s",
                self._settings.mqtt_notification_topic,
                result,
            )

    def _on_disconnect(self, client, userdata, rc, *args) -> None:
        logger.warning("Notification MQTT disconnected: rc=%s", rc)

    def _on_message(self, client, userdata, message) -> None:
        envelope = IncomingMqttMessage(
            topic=message.topic,
            payload=bytes(message.payload),
            qos=message.qos,
            mid=message.mid,
            client=client,
        )
        if self._loop is None:
            logger.error("Notification MQTT loop is unavailable; message left unacked")
            return
        self._loop.call_soon_threadsafe(self._enqueue_message, envelope)

    def _enqueue_message(self, message: IncomingMqttMessage) -> None:
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            logger.error(
                "Notification MQTT queue full; message left unacked: topic=%s mid=%s",
                message.topic,
                message.mid,
            )

    async def _consume(self) -> None:
        while True:
            message = await self._queue.get()
            try:
                try:
                    await self._worker.handle_message(message)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Unhandled notification message error; message left unacked: "
                        "topic=%s mid=%s",
                        message.topic,
                        message.mid,
                    )
            finally:
                self._queue.task_done()

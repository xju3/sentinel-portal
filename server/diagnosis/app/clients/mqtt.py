import asyncio
import json
import logging
from typing import Any

from pub.clients.mqtt import MQTTManager

from app.config import settings

logger = logging.getLogger(__name__)


def _on_connect(client, userdata, flags, rc, *args) -> None:
    if rc == 0:
        logger.info("Diagnosis publisher connected to MQTT broker")
    else:
        logger.error("Diagnosis publisher MQTT connect failed: rc=%s", rc)


def _on_disconnect(client, userdata, rc, *args) -> None:
    logger.warning("Diagnosis publisher disconnected from MQTT broker: rc=%s", rc)


diagnosis_mqtt_manager = MQTTManager(
    on_connect_callback=_on_connect,
    on_disconnect_callback=_on_disconnect,
)


async def publish_notification_event(event: dict[str, Any]) -> bool:
    payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    published = await asyncio.to_thread(
        diagnosis_mqtt_manager.publish_confirmed,
        settings.mqtt_notification_topic,
        payload,
        1,
        settings.mqtt_publish_timeout_seconds,
    )
    if not published:
        logger.error(
            "Failed to publish diagnosis notification event: "
            "event_id=%s diagnosis_id=%s device_id=%s level=%s faults=%s",
            event.get("event_id"),
            event.get("diagnosis_id"),
            event.get("device_id"),
            event.get("overall_level"),
            event.get("faults"),
        )
    return published

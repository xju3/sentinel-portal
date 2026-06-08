"""
MQTT message handler
"""

import json
import logging
from typing import Any

from app.clients.dia_influxdb_client import send_vibration_features_to_telegraf
from app.config import settings
from app.database import minio_manager
from app.handler.diagnosis import start_diagnosis_async
from pub.clients.mqtt import MQTTManager
from pub.clients.minio import download_json_from_minio_sync

logger = logging.getLogger(__name__)
REQUIRED_AXES = frozenset({"X", "Y", "Z"})


class DiaMqttClient:
    """Handler for MinIO object notifications from sensor data ingestion."""

    def __init__(self) -> None:
        self.mqtt_manager: MQTTManager | None = None

    def start(self) -> None:
        """Register callbacks, start the MQTT client, and inject event loop."""

        def on_mqtt_connect(client, userdata, flags, rc, *args):
            logger.info(f"Subscribing to topic: '{settings.mqtt_topic}'")
            client.subscribe(settings.mqtt_topic)

        def on_mqtt_message(client, userdata, msg):
            logger.info(
                f"Received MQTT message on topic '{msg.topic}' with payload: {msg.payload}"
            )
            self.handle_message(msg.topic, msg.payload)

        self.mqtt_manager = MQTTManager(
            on_connect_callback=on_mqtt_connect,
            on_message_callback=on_mqtt_message,
        )
        self.mqtt_manager.init()

    def handle_message(self, topic: str, payload: bytes) -> None:
        """Handle an incoming MQTT message.

        Parses the JSON payload to extract bucket and path, then fetches
        the file from MinIO and writes vibration features to InfluxDB via Telegraf.

        Args:
            topic: The MQTT topic the message was published on.
            payload: The raw message payload (bytes).
        """
        logger.info(f"[DiagnosisticHandler] Received message on topic '{topic}'")

        try:
            data = json.loads(payload.decode("utf-8"))
            logger.info(f"Parsed notification payload: {data}")
            bucket_name = self._require_notification_value(data, "bucket")
            object_name = self._require_notification_value(data, "path")

            sensor_payload = download_json_from_minio_sync(
                minio_client=minio_manager.get_client(),
                bucket_name=bucket_name,
                object_name=object_name,
            )

            logger.info(
                f"Downloaded JSON from MinIO: bucket='{bucket_name}', object='{object_name}'"
            )
            present_axes = self._present_payload_axes(sensor_payload)
            missing_axes = REQUIRED_AXES - present_axes
            if missing_axes:
                logger.warning(
                    "Abort ingestion for MinIO JSON %s/%s: missing vibration axes %s, "
                    "present axes %s",
                    bucket_name,
                    object_name,
                    sorted(missing_axes),
                    sorted(present_axes),
                )
                return

            sn = self._require_payload_str(sensor_payload, "sn")
            temperature_c = self._require_payload_number(sensor_payload, "temperature_c")
            ts_ms = self._require_payload_int(sensor_payload, "ts_ms")
            report_id, point_count = send_vibration_features_to_telegraf(sensor_payload)
            logger.info(
                "Processed MinIO JSON notification %s/%s into %s vibration feature points "
                "with report_id=%s",
                bucket_name,
                object_name,
                point_count,
                report_id,
            )
            start_diagnosis_async(report_id, sn, temperature_c, ts_ms)

        except Exception as e:
            logger.error(f"Failed to process message: {e}", exc_info=True)

    @staticmethod
    def _require_notification_value(data: dict[str, Any], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"MQTT notification missing non-empty '{key}'")
        return value


    @staticmethod
    def _present_payload_axes(payload: dict[str, Any]) -> set[str]:
        axis_features = payload.get("axis_features")
        if not isinstance(axis_features, dict):
            return set()
        return {
            axis
            for axis in REQUIRED_AXES
            if isinstance(axis_features.get(axis), dict)
        }

    @staticmethod
    def _require_payload_str(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"sensor payload missing non-empty '{key}'")
        return value

    @staticmethod
    def _require_payload_number(payload: dict[str, Any], key: str) -> float:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"sensor payload.{key} must be numeric")
        return float(value)

    @staticmethod
    def _require_payload_int(payload: dict[str, Any], key: str) -> int:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"sensor payload.{key} must be an integer")
        return value


dia_mqtt_client = DiaMqttClient()

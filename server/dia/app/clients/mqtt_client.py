"""
MQTT message handler
"""

import asyncio
import json
import logging
from typing import Any

from app.clients.influxdb_client import send_vibration_features_to_telegraf
from app.config import settings
from app.database import minio_manager, redis_manager
from pub.utils.redis_keys import REDIS_KEY_SENSOR_META
from pub.clients.mqtt import MQTTManager
from pub.clients.minio import download_json_from_minio_sync
from app.handler.diagnosis import start_diagnosis_async
from pub.services import SensorCommunicationService

logger = logging.getLogger(__name__)


class DiaMqttClient:
    """Handler for MinIO object notifications from sensor data ingestion."""

    def __init__(self) -> None:
        self.mqtt_manager: MQTTManager | None = None

    def start(self) -> None:
        """Register callbacks, start the MQTT client, and inject event loop."""

        def on_mqtt_connect(client, userdata, flags, rc, *args):
            # logger.info(f"Subscribing to topic: '{settings.mqtt_topic}'")
            client.subscribe(settings.mqtt_topic)

        def on_mqtt_message(client, userdata, msg):
            # logger.info(
            #     f"Received MQTT message on topic '{msg.topic}' with payload: {msg.payload}"
            # )
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
        # logger.info(f"[DiagnosisticHandler] Received message on topic '{topic}'")

        try:
            data = json.loads(payload.decode("utf-8"))
            # logger.info(f"Parsed notification payload: {data}")
            if "bucket" in data and "path" in data:
                bucket_name = self._require_notification_value(data, "bucket")
                object_name = self._require_notification_value(data, "path")
    
                sensor_payload = download_json_from_minio_sync(
                    minio_client=minio_manager.get_client(),
                    bucket_name=bucket_name,
                    object_name=object_name,
                )
            else:
                # Raw sensor data directly uploaded via MQTT
                sensor_payload = data
                bucket_name = "mqtt_raw"
                object_name = "direct"
                
                sn = sensor_payload.get("sensor_sn") or sensor_payload.get("sn")
                if sn:
                    if "sn" in sensor_payload:
                        del sensor_payload["sn"]
                    sensor_payload["sensor_sn"] = sn
                    
                    redis_client = redis_manager.get_client()
                    if redis_client:
                        meta_str = redis_client.get(REDIS_KEY_SENSOR_META.format(sn=sn))
                        if meta_str:
                            try:
                                meta = json.loads(meta_str)
                                sensor_payload.update(meta)
                            except Exception as e:
                                logger.error(f"Failed to parse sensor metadata from redis for {sn}: {e}")
            try:
                communication_record = asyncio.run(
                    SensorCommunicationService.record_from_payload_managed(sensor_payload)
                )
                if communication_record is not None:
                    logger.debug(
                        "Sensor communication timing saved: sn=%s ts_ms=%s duration_ms=%s sequence=%s",
                        communication_record.sn,
                        communication_record.ts_ms,
                        communication_record.duration_ms,
                        communication_record.sequence,
                    )
            except Exception as e:
                logger.error("Failed to save sensor communication timing: %s", e, exc_info=True)

            # logger.info(f"Downloaded JSON from MinIO: bucket='{bucket_name}', object='{object_name}'")
            report_id, point_count = send_vibration_features_to_telegraf(sensor_payload)
            logger.debug(
                "Processed MinIO JSON notification %s/%s into %s vibration feature points "
                "with report_id=%s", bucket_name, object_name, point_count, report_id,
            )

            sn = sensor_payload.get("sn")
            temperature_c = sensor_payload.get("temperature_c")
            ts_ms = sensor_payload.get("ts_ms")
            if sn and temperature_c is not None and ts_ms is not None:
                start_diagnosis_async(
                    report_id=report_id,
                    sn=sn,
                    current_temperature_c=float(temperature_c),
                    current_ts_ms=int(ts_ms),
                    payload=sensor_payload,
                )
            
        except Exception as e:
            logger.error(f"Failed to process message: {e}", exc_info=True)

    @staticmethod
    def _require_notification_value(data: dict[str, Any], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"MQTT notification missing non-empty '{key}'")
        return value

dia_mqtt_client = DiaMqttClient()

"""
MQTT message handler
"""

import asyncio
import logging
import json
from typing import Any, Optional

from pub.models.message_pb2 import MsgRmsReport
from pub.clients.mqtt import MQTTManager
from pub.services.diagnosis_service import PatrolDiagnosisRecordService
from app.config import settings

from app.clients.redis import redis_client

logger = logging.getLogger(__name__)


class DiaMqttClient:
    """Handler for patrol (巡检) MQTT messages.

    Parses protobuf-encoded MsgRmsReport messages and pushes
    the relevant data (rms_m, temperature) into a Redis queue.
    """

    def __init__(self) -> None:
        self._redis_client = redis_client
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.mqtt_manager: Optional[MQTTManager] = None

    def _set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the asyncio event loop for scheduling async tasks from sync context."""
        self._loop = loop

    def _parse_payload(self, payload: bytes) -> Optional[MsgRmsReport]:
        """Parse the protobuf payload into a MsgRmsReport message.

        Args:
            payload: The raw message payload (bytes).

        Returns:
            A MsgRmsReport instance, or None if parsing fails.
        """
        try:
            report = MsgRmsReport()
            report.ParseFromString(payload)
            return report
        except Exception as e:
            logger.error(f"Failed to parse protobuf payload: {e}")
            return None

    def _run_async(self, coro) -> Any:
        """Run an async coroutine from a sync context and return its result.

        Args:
            coro: The coroutine to execute.

        Returns:
            The result of the coroutine, or None if the event loop is unavailable.
        """
        if self._loop is not None and not self._loop.is_closed():
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return future.result()
        logger.warning("Event loop not available, skipping async operation")
        return None

    def start(self) -> None:
        """Register callbacks, start the MQTT client, and inject event loop."""
        def on_mqtt_connect(client, userdata, flags, rc, *args):
            logger.info(f"Subscribing to topic: '{settings.mqtt_topic}'")
            client.subscribe(settings.mqtt_topic)
            
        def on_mqtt_message(client, userdata, msg):
            logger.info(f"Received MQTT message on topic '{msg.topic}' with payload: {msg.payload}")
            self.handle_message(msg.topic, msg.payload)
            
        self.mqtt_manager = MQTTManager(
            on_connect_callback=on_mqtt_connect,
            on_message_callback=on_mqtt_message
        )
        self.mqtt_manager.init()


    def handle_message(self, topic: str, payload: bytes) -> None:
        """Handle an incoming MQTT message.

        Parses the JSON payload to extract bucket and path, then fetches 
        the file from MinIO to process diagnosis.

        Args:
            topic: The MQTT topic the message was published on.
            payload: The raw message payload (bytes).
        """
        logger.info(f"[DiagnosisticHandler] Received message on topic '{topic}'")
        
        try:
            data = json.loads(payload.decode('utf-8'))
            logger.info(f"Parsed notification payload: {data}")
            # TODO: 结合 MinIOManager 下载 data['bucket'] 和 data['path'] 对应的 json 文件以继续诊断逻辑
        except Exception as e:
            logger.error(f"Failed to process message: {e}")


               
dia_mqtt_client = DiaMqttClient() 
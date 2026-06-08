"""
MQTT message handler
"""

import asyncio
import logging
import json
from typing import Any, Optional

from pub.models.message_pb2 import MsgRmsReport
from pub.clients.mqtt import mqtt_manager
from pub.services.diagnosis_service import PatrolDiagnosisRecordService
from app.config import settings

from app.clients.redis import redis_client

logger = logging.getLogger(__name__)


class DiagnosisticHandler:
    """Handler for patrol (巡检) MQTT messages.

    Parses protobuf-encoded MsgRmsReport messages and pushes
    the relevant data (rms_m, temperature) into a Redis queue.
    """

    def __init__(self) -> None:
        self._redis_client = redis_client
        self._loop: Optional[asyncio.AbstractEventLoop] = None

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
            self.handle_message(msg.topic, msg.payload)
            
        mqtt_manager.register_on_connect(on_mqtt_connect)
        mqtt_manager.register_on_message(on_mqtt_message)
        mqtt_manager.init()

        # Inject the running event loop into handler
        self._set_loop(asyncio.get_running_loop())

    def handle_message(self, topic: str, payload: bytes) -> None:
        """Handle an incoming MQTT message.

        Parses the protobuf payload to extract the SN, rms_m, and temperature,
        then pushes the data into a fixed-length Redis queue.

        Args:
            topic: The MQTT topic the message was published on.
            payload: The raw message payload (bytes).
        """
        # logger.info(f"[PatrolMsgHandler] Received message on topic '{topic}': {payload}")

        # Parse protobuf payload
        report = self._parse_payload(payload)
        if not report:
            logger.warning("Failed to parse payload")
            return

        sn = str(report.sn)
        logger.info(
            f"Parsed message: SN={sn}, rms_m={report.rms_m}, temperature={report.temperature}"
        )
       
handler = DiagnosisticHandler() 
import asyncio
import logging

from pydantic import ValidationError

from app.clients.mqtt import IncomingMqttMessage
from app.services.notification_service import NotificationServiceProtocol

logger = logging.getLogger(__name__)


class NotificationWorker:
    def __init__(self, notification_service: NotificationServiceProtocol):
        self._notification_service = notification_service

    async def handle_message(self, message: IncomingMqttMessage) -> bool:
        try:
            event = self._notification_service.parse_event(message.payload)
        except (ValidationError, ValueError, UnicodeDecodeError):
            logger.error(
                "Dropping invalid notification event: topic=%s payload=%r",
                message.topic,
                message.payload,
                exc_info=True,
            )
            await self._ack(message)
            return False

        try:
            await self._notification_service.process_event(event)
        except Exception:  # noqa: BLE001
            logger.error(
                "Notification processing failed; MQTT message left unacked: topic=%s mid=%s diagnosis_id=%s",
                message.topic,
                message.mid,
                event.diagnosis_id,
                exc_info=True,
            )
            return False

        await self._ack(message)
        return True

    async def _ack(self, message: IncomingMqttMessage) -> None:
        rc = await asyncio.to_thread(message.client.ack, message.mid, message.qos)
        if rc != 0:
            logger.error(
                "Notification MQTT ack failed: topic=%s mid=%s rc=%s",
                message.topic,
                message.mid,
                rc,
            )

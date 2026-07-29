import logging
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pub.services.notification import (
    DiagnosisNotificationEvent,
    NotificationService,
)

from app.config import Settings
from app.services.formatter import NotificationTemplateContext, build_template_data

logger = logging.getLogger(__name__)

NotificationEvent = DiagnosisNotificationEvent


class NotificationServiceProtocol(Protocol):
    def parse_event(
        self,
        payload: dict[str, Any] | str | bytes,
    ) -> DiagnosisNotificationEvent:
        """Validate and normalize one MQTT event."""

    async def process_event(
        self,
        event: DiagnosisNotificationEvent,
    ) -> dict[str, int | str]:
        """Handle one validated notification event."""


class LocalNotificationService(NotificationServiceProtocol):
    """Coordinates durable delivery records with the existing WeChat API."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        wx_service: Any,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._wx_service = wx_service
        self._settings = settings
        self._timezone = ZoneInfo(settings.notification_timezone)

    @staticmethod
    def parse_event(
        payload: dict[str, Any] | str | bytes,
    ) -> DiagnosisNotificationEvent:
        return NotificationService.parse_event(payload)

    async def process_event(
        self,
        event: DiagnosisNotificationEvent,
    ) -> dict[str, int | str]:
        async with self._session_factory() as session:
            targets = await NotificationService.prepare_delivery_targets(session, event)

        sent = 0
        failed = 0
        skipped = 0
        for target in targets:
            if not target.should_send:
                skipped += 1
                continue

            # Resolve every database-backed message field before claiming the
            # delivery. A transient context query failure therefore leaves the
            # row PENDING and safe for MQTT redelivery.
            async with self._session_factory() as session:
                context = await NotificationService.get_message_context(
                    session,
                    target.delivery_id,
                )

            async with self._session_factory() as session:
                claimed = await NotificationService.mark_delivery_sending(
                    session,
                    target.delivery_id,
                )
            if not claimed:
                skipped += 1
                continue

            try:
                if context is None:
                    raise RuntimeError(
                        f"Notification delivery not found: {target.delivery_id}"
                    )

                descriptions = "；".join(context.diagnosis_items)
                template_data = build_template_data(
                    NotificationTemplateContext(
                        device_code=context.device_code or str(context.device_id),
                        device_name=context.device_name or "未知设备",
                        diagnosed_at=context.diagnosed_at.astimezone(self._timezone),
                        fault_description=descriptions or context.overall_level_label,
                        level_label=context.overall_level_label,
                    )
                )
                result = await self._wx_service.send_template_message(
                    to_user_openid=target.wx_user_id,
                    template_id=self._settings.wx_template_id,
                    data=template_data,
                    url=self._settings.wx_template_url,
                )
                if not result:
                    raise RuntimeError("WeChat service returned false")
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "WeChat notification delivery failed: delivery_id=%s employee_id=%s",
                    target.delivery_id,
                    target.employee_id,
                    exc_info=True,
                )
                async with self._session_factory() as session:
                    await NotificationService.mark_delivery_failed(
                        session,
                        target.delivery_id,
                        str(exc),
                    )
                failed += 1
                continue

            async with self._session_factory() as session:
                await NotificationService.mark_delivery_sent(
                    session,
                    target.delivery_id,
                )
            sent += 1

        status = "no_recipients" if not targets else "processed"
        return {
            "status": status,
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
        }

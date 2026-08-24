import logging
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pub.services.notification import (
    DiagnosisNotificationEvent,
    DiagnosisNotificationFaultEvent,
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
        sent = 0
        failed = 0
        deferred = 0
        skipped = 0
        target_count = 0
        for fault_event in event.expanded_faults():
            async with self._session_factory() as session:
                should_notify = await NotificationService.should_notify_fault(
                    session,
                    fault_event,
                    confirmation_count=(
                        self._settings.bearing_notification_confirmation_count
                    ),
                    window_hours=self._settings.bearing_notification_window_hours,
                    immediate_level=(
                        self._settings.bearing_notification_immediate_level
                    ),
                )
            if not should_notify:
                skipped += 1
                continue

            async with self._session_factory() as session:
                targets = await NotificationService.prepare_delivery_targets(
                    session,
                    fault_event,
                    max_attempts=self._settings.notification_delivery_max_attempts,
                )

            target_count += len(targets)
            for target in targets:
                if not target.should_send:
                    skipped += 1
                    if target.skip_reason == "retry_wait":
                        deferred += 1
                    continue

                # Resolve every database-backed message field before claiming the
                # delivery. A transient context query failure therefore leaves the
                # row PENDING and safe for MQTT redelivery.
                async with self._session_factory() as session:
                    context = await NotificationService.get_message_context(
                        session,
                        target.delivery_id,
                        event=fault_event,
                    )

                async with self._session_factory() as session:
                    claimed = await NotificationService.mark_delivery_sending(
                        session,
                        target.delivery_id,
                        max_attempts=self._settings.notification_delivery_max_attempts,
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
                            fault_description=descriptions
                            or f"{context.fault_label}{context.fault_level_label}",
                            level_label=context.fault_level_label,
                        )
                    )
                    result = await self._wx_service.send_template_message(
                        to_user_openid=target.wx_user_id,
                        template_id=self._settings.wx_template_id,
                        data=template_data,
                        url=self._build_detail_url(context, fault_event),
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
                            retry_after_seconds=(
                                self._settings.notification_delivery_retry_seconds
                            ),
                        )
                    failed += 1
                    continue

                async with self._session_factory() as session:
                    await NotificationService.mark_delivery_sent(
                        session,
                        target.delivery_id,
                    )
                sent += 1

        if failed or deferred:
            raise RuntimeError(
                "WeChat diagnosis notification delivery incomplete: "
                f"failed={failed} deferred={deferred}"
            )
        status = "no_recipients" if target_count == 0 else "processed"
        return {
            "status": status,
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
        }

    def _build_detail_url(
        self,
        context: Any,
        event: DiagnosisNotificationFaultEvent,
    ) -> str | None:
        base_url = self._settings.wx_template_url
        if not base_url:
            return None

        params = {
            "delivery_id": str(context.delivery_id),
            "fault_type": event.fault_type,
        }
        if context.report_id is not None:
            params["report_id"] = str(context.report_id)
        if context.diagnosis_item_id is not None:
            params["diagnosis_item_id"] = str(context.diagnosis_item_id)

        parts = urlsplit(base_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.update(params)
        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urlencode(query),
                parts.fragment,
            )
        )

"""Reliable diagnosis notification outbox dispatcher."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import or_, select

from app.clients.mqtt import publish_notification_event
from app.config import settings
from pub.manager.database import db_manager
from pub.models.diagnosis import (
    DiagnosisNotificationOutbox,
    DiagnosisNotificationOutboxStatus,
)

logger = logging.getLogger(__name__)


def retry_delay_seconds(attempt_count: int) -> float:
    """Return a bounded exponential retry delay."""
    exponent = max(0, min(attempt_count - 1, 10))
    return min(
        settings.notification_outbox_max_backoff_seconds,
        settings.notification_outbox_initial_backoff_seconds * (2**exponent),
    )


async def dispatch_pending_notification_events(
    *,
    limit: int | None = None,
) -> int:
    """Publish a bounded batch while row locks prevent replica duplication."""
    if db_manager.SessionLocal is None:
        return 0

    batch_limit = limit or settings.notification_outbox_batch_size
    published_count = 0

    for _ in range(batch_limit):
        now = datetime.utcnow()
        async with db_manager.SessionLocal() as session:
            async with session.begin():
                stmt = (
                    select(DiagnosisNotificationOutbox)
                    .where(
                        DiagnosisNotificationOutbox.status.in_(
                            [
                                DiagnosisNotificationOutboxStatus.PENDING.value,
                                DiagnosisNotificationOutboxStatus.FAILED.value,
                            ]
                        ),
                        or_(
                            DiagnosisNotificationOutbox.next_attempt_at.is_(None),
                            DiagnosisNotificationOutbox.next_attempt_at <= now,
                        ),
                    )
                    .order_by(DiagnosisNotificationOutbox.created_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                outbox = (await session.execute(stmt)).scalar_one_or_none()
                if outbox is None:
                    break

                outbox.attempt_count = int(outbox.attempt_count or 0) + 1
                try:
                    published = await publish_notification_event(outbox.payload)
                except Exception as exc:  # pragma: no cover - defensive boundary
                    published = False
                    outbox.last_error = str(exc)[:1024]
                    logger.exception(
                        "Diagnosis notification outbox publish raised: event_id=%s",
                        outbox.event_id,
                    )

                if published:
                    outbox.status = (
                        DiagnosisNotificationOutboxStatus.PUBLISHED.value
                    )
                    outbox.published_at = now
                    outbox.next_attempt_at = None
                    outbox.last_error = None
                    published_count += 1
                else:
                    outbox.status = DiagnosisNotificationOutboxStatus.FAILED.value
                    outbox.last_error = (
                        outbox.last_error or "MQTT publish was not acknowledged"
                    )[:1024]
                    outbox.next_attempt_at = now + timedelta(
                        seconds=retry_delay_seconds(outbox.attempt_count)
                    )

    return published_count


async def run_notification_outbox_dispatcher() -> None:
    """Continuously bridge committed outbox rows to MQTT."""
    while True:
        try:
            published = await dispatch_pending_notification_events()
            if published == 0:
                await asyncio.sleep(settings.notification_outbox_poll_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Diagnosis notification outbox dispatcher failed")
            await asyncio.sleep(settings.notification_outbox_poll_seconds)

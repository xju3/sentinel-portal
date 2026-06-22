"""
Sensor communication timing persistence.
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pub.manager.database import db_manager
from pub.models.sensor import CommunicationRecord, CommunicationState, Sensor

logger = logging.getLogger(__name__)


class SensorCommunicationService:
    """Store sensor collection communication timing and maintain per-SN state."""

    @staticmethod
    def payload_to_event(payload: dict[str, Any]) -> dict[str, Any] | None:
        """Extract the communication event from a result JSON payload."""
        sn = payload.get("sn")
        ts_ms = payload.get("ts_ms")
        duration_ms = payload.get("duration_ms", payload.get("druation_ms"))
        if not sn or ts_ms is None or duration_ms is None:
            return None

        return {
            "sn": str(sn),
            "ts_ms": int(ts_ms),
            "duration_ms": float(duration_ms),
        }

    @staticmethod
    async def record_from_payload_managed(
        payload: dict[str, Any],
    ) -> CommunicationRecord | None:
        """Persist communication timing from a result JSON payload."""
        event = SensorCommunicationService.payload_to_event(payload)
        if event is None:
            return None

        return await SensorCommunicationService.record_managed(**event)

    @staticmethod
    async def record_managed(
        sn: str,
        ts_ms: int,
        duration_ms: float,
    ) -> CommunicationRecord | None:
        """Persist communication timing using an internally managed session."""
        if db_manager.SessionLocal is None:
            raise RuntimeError("Database not initialized. Call db_manager.init() first.")

        await db_manager.ensure_schema()
        for attempt in range(3):
            try:
                async with db_manager.SessionLocal() as session:
                    return await SensorCommunicationService.record(
                        session=session,
                        sn=sn,
                        ts_ms=ts_ms,
                        duration_ms=duration_ms,
                    )
            except IntegrityError as e:
                logger.warning(
                    "Retrying communication record after sequence conflict: sn=%s attempt=%s error=%s",
                    sn,
                    attempt + 1,
                    e,
                )
        logger.error("Failed to save communication record after retries: sn=%s ts_ms=%s", sn, ts_ms)
        return None

    @staticmethod
    async def record(
        session: AsyncSession,
        sn: str,
        ts_ms: int,
        duration_ms: float,
    ) -> CommunicationRecord:
        """Create a communication record and update latest sensor activity."""
        now = datetime.utcnow()
        activity_at = datetime.utcfromtimestamp(ts_ms / 1000.0)

        result = await session.execute(
            select(CommunicationState)
            .where(CommunicationState.sn == sn)
            .with_for_update()
        )
        state = result.scalar_one_or_none()
        if state is None:
            state = CommunicationState(sn=sn, last_sequence=0, created_at=now)
            session.add(state)
            await session.flush()

        sequence = int(state.last_sequence or 0) + 1
        state.last_sequence = sequence
        state.last_ts_ms = ts_ms
        state.last_duration_ms = duration_ms
        state.last_activity_at = activity_at
        state.updated_at = now

        record = CommunicationRecord(
            sn=sn,
            ts_ms=ts_ms,
            duration_ms=duration_ms,
            sequence=sequence,
            created_at=now,
        )
        session.add(record)

        await session.execute(
            update(Sensor)
            .where(Sensor.sn == sn)
            .values(active_at=activity_at, updated_at=now)
        )
        await session.commit()
        await session.refresh(record)
        return record

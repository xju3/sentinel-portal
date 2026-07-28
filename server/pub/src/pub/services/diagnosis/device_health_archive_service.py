"""Device health archive timeline queries."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pub.models.diagnosis import DiagnosisRecord, DiagnosisRecordStatus


LEVEL_NAMES = {
    0: "normal",
    1: "attention",
    2: "abnormal",
    3: "warning",
    4: "critical",
}


def _iso_utc(ts_ms: int) -> str:
    return (
        datetime.fromtimestamp(ts_ms / 1000, timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


class DeviceHealthArchiveService:
    DEFAULT_RANGE_DAYS = 7
    MAX_RANGE_DAYS = 366

    @staticmethod
    def normalize_range(
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> tuple[datetime, datetime]:
        end = end_at or datetime.now(timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        else:
            end = end.astimezone(timezone.utc)

        start = start_at or (end - timedelta(days=DeviceHealthArchiveService.DEFAULT_RANGE_DAYS))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        else:
            start = start.astimezone(timezone.utc)

        if start >= end:
            raise ValueError("start_at must be earlier than end_at")
        if end - start > timedelta(days=DeviceHealthArchiveService.MAX_RANGE_DAYS):
            raise ValueError(
                f"time range cannot exceed {DeviceHealthArchiveService.MAX_RANGE_DAYS} days"
            )
        return start, end

    @staticmethod
    async def get_timeline(
        session: AsyncSession,
        tenant_id: UUID,
        device_id: UUID,
        start_at: datetime,
        end_at: datetime,
        interval_hours: int,
    ) -> dict[str, Any]:
        start_ms = int(start_at.timestamp() * 1000)
        end_ms = int(end_at.timestamp() * 1000)
        interval_ms = interval_hours * 3600 * 1000

        statement = (
            select(DiagnosisRecord)
            .where(
                DiagnosisRecord.tenant_id == tenant_id,
                DiagnosisRecord.device_id == device_id,
                DiagnosisRecord.ts_ms >= start_ms,
                DiagnosisRecord.ts_ms < end_ms,
                DiagnosisRecord.diagnosis_status
                != int(DiagnosisRecordStatus.SKIPPED),
            )
            .order_by(DiagnosisRecord.ts_ms.asc())
        )
        records = (await session.execute(statement)).scalars().all()
        return DeviceHealthArchiveService.build_timeline(
            records=records,
            start_ms=start_ms,
            end_ms=end_ms,
            interval_ms=interval_ms,
        )

    @staticmethod
    def build_timeline(
        records: list[DiagnosisRecord],
        start_ms: int,
        end_ms: int,
        interval_ms: int,
    ) -> dict[str, Any]:
        bucket_count = math.ceil((end_ms - start_ms) / interval_ms)
        buckets = [
            {
                "startAt": _iso_utc(start_ms + index * interval_ms),
                "endAt": _iso_utc(min(start_ms + (index + 1) * interval_ms, end_ms)),
                "status": "no_data",
                "level": None,
                "diagnosedCount": 0,
                "normalCount": 0,
                "abnormalCount": 0,
                "missedCount": 0,
                "waitingCount": 0,
                "receivedCount": 0,
                "hasGap": False,
            }
            for index in range(bucket_count)
        ]

        summary = {
            "diagnosedCount": 0,
            "normalCount": 0,
            "abnormalCount": 0,
            "missedCount": 0,
            "waitingCount": 0,
            "receivedCount": 0,
        }

        for record in records:
            index = (record.ts_ms - start_ms) // interval_ms
            if index < 0 or index >= bucket_count:
                continue
            bucket = buckets[index]
            status = int(record.diagnosis_status)

            if status == int(DiagnosisRecordStatus.DIAGNOSED):
                level = int(record.overall_level or 0)
                bucket["diagnosedCount"] += 1
                summary["diagnosedCount"] += 1
                if level == 0:
                    bucket["normalCount"] += 1
                    summary["normalCount"] += 1
                else:
                    bucket["abnormalCount"] += 1
                    summary["abnormalCount"] += 1
                bucket["level"] = max(bucket["level"] or 0, level)
            elif status == int(DiagnosisRecordStatus.MISSED):
                bucket["missedCount"] += 1
                summary["missedCount"] += 1
            elif status == int(DiagnosisRecordStatus.WAITING):
                bucket["waitingCount"] += 1
                summary["waitingCount"] += 1
            elif status == int(DiagnosisRecordStatus.RECEIVED):
                bucket["receivedCount"] += 1
                summary["receivedCount"] += 1

        for bucket in buckets:
            bucket["hasGap"] = bucket["missedCount"] > 0
            if bucket["diagnosedCount"] > 0:
                bucket["status"] = LEVEL_NAMES[bucket["level"]]
            elif bucket["missedCount"] > 0:
                bucket["status"] = "missed"
            elif bucket["waitingCount"] > 0:
                bucket["status"] = "waiting"
            elif bucket["receivedCount"] > 0:
                bucket["status"] = "processing"

        return {
            "range": {
                "startAt": _iso_utc(start_ms),
                "endAt": _iso_utc(end_ms),
                "intervalHours": interval_ms // (3600 * 1000),
                "bucketCount": bucket_count,
            },
            "summary": summary,
            "buckets": buckets,
        }

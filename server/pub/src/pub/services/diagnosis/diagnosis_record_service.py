"""
Diagnosis service - business logic for patrol diagnosis record operations
"""

import logging
from typing import Any, Optional
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, update
from pub.manager.database import db_manager
from pub.models.diagnosis import DiagnosisRecord, DiagnosisRecordStatus

logger = logging.getLogger(__name__)


def initial_diagnosis_status(delay: int, total: int) -> DiagnosisRecordStatus:
    if delay > 0:
        return DiagnosisRecordStatus.SKIPPED
    if total > 0:
        return DiagnosisRecordStatus.WAITING
    return DiagnosisRecordStatus.RECEIVED


def _parse_quality_status(quality: Any) -> int:
    """Parse the raw quality object to determine the integer quality_status (0=usable, 1=unusable)."""
    if not isinstance(quality, dict):
        return 1
    status = quality.get("status")
    if status == 0 or status == "ok":
        return 0
    return 1

class DiagnosisRecordService:
    """Service for managing the parent DiagnosisRecord."""

    @staticmethod
    async def create_managed(
        report_id: str,
        sn: str,
        report_ts: int,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> Optional[DiagnosisRecord]:
        """Create a new DiagnosisRecord using an internally managed session."""
        if db_manager.SessionLocal is None:
            raise RuntimeError("Database not initialized.")
            
        if not context or "monitoring" not in context or not context["monitoring"]:
            logger.warning(f"No monitoring context for sn {sn}, skipping diagnosis record creation.")
            return None

        try:
            await db_manager.ensure_schema()
            async with db_manager.SessionLocal() as session:
                monitoring = context["monitoring"]
                device_id = monitoring.get("device_inst_id")
                
                sensor_ctx = context.get("sensor") or {}
                device_inst = context.get("device_inst") or {}
                device_category = context.get("device_category") or {}
                peer_group = context.get("peer_group") or {}
                process_device = peer_group.get("process_device") or {} if peer_group else {}
                delay = int(payload.get("delay") or 0)
                total = int(payload.get("total") or 0)
                diagnosis_status = initial_diagnosis_status(delay, total)
                
                record = DiagnosisRecord(
                    id=UUID(report_id) if report_id else None,
                    schema_version=payload.get("schema_version"),
                    sensor_sn=sensor_ctx.get("sn") or payload.get("sensor_sn") or sn,
                    device_id=UUID(device_inst.get("id")) if device_inst.get("id") else None,
                    temperature_c=payload.get("temperature_c"),
                    fs_hz=payload.get("fs_hz"),
                    requested_range_g=payload.get("requested_range_g"),
                    range_g=payload.get("range_g"),
                    points=payload.get("points"),
                    task_id=payload.get("task_id") if payload.get("task_id") and str(payload.get("task_id")).strip() else None,
                    sample_type=payload.get("sample_type"),
                    duration_ms=payload.get("duration_ms"),
                    quality=payload.get("quality"),
                    delay=delay,
                    total=total,
                    diagnosis_status=diagnosis_status,
                    sensor_id=UUID(sensor_ctx.get("id")) if sensor_ctx.get("id") else None,
                    location_id=UUID(monitoring.get("location_id")) if monitoring.get("location_id") else None,
                    tenant_id=UUID(device_category.get("tenant_id")) if device_category.get("tenant_id") else None,
                    region_id=payload.get("region_id"),
                    device_category_id=UUID(device_category.get("id")) if device_category.get("id") else None,
                    process_device_id=UUID(process_device.get("id")) if process_device.get("id") else None,
                    rpm=payload.get("rpm"),
                    ts_ms=report_ts
                )
                session.add(record)
                await session.commit()
                await session.refresh(record)
                return record
        except Exception as e:
            logger.error("Failed to create diagnosis record: %s", e)
            return None

    @staticmethod
    async def update_status_managed(
        report_id: str,
        status: DiagnosisRecordStatus | int,
        overall_level: int | None = None,
        diagnosed_at: datetime | None = None,
    ) -> bool:
        """Update the health-archive state of a DiagnosisRecord."""
        if db_manager.SessionLocal is None:
            return False
            
        try:
            async with db_manager.SessionLocal() as session:
                stmt = select(DiagnosisRecord).where(
                    DiagnosisRecord.id == UUID(report_id)
                )
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()
                if record:
                    record.diagnosis_status = int(status)
                    if overall_level is not None:
                        record.overall_level = overall_level
                    if int(status) == int(DiagnosisRecordStatus.DIAGNOSED):
                        record.diagnosed_at = diagnosed_at or datetime.now(
                            timezone.utc
                        ).replace(tzinfo=None)
                    await session.commit()
                    return True
                return False
        except Exception as e:
            logger.error("Failed to update diagnosis record status: %s", e)
            return False

    @staticmethod
    async def mark_waiting_as_missed_managed(
        device_id: str,
        current_report_id: str,
    ) -> bool:
        """Close unfinished waiting cycles when a new delay=0 report arrives."""
        if db_manager.SessionLocal is None:
            return False

        try:
            async with db_manager.SessionLocal() as session:
                statement = (
                    update(DiagnosisRecord)
                    .where(
                        DiagnosisRecord.device_id == UUID(device_id),
                        DiagnosisRecord.diagnosis_status
                        == int(DiagnosisRecordStatus.WAITING),
                        DiagnosisRecord.id != UUID(current_report_id),
                    )
                    .values(diagnosis_status=int(DiagnosisRecordStatus.MISSED))
                )
                await session.execute(statement)
                await session.commit()
                return True
        except Exception as e:
            logger.error("Failed to close waiting diagnosis records: %s", e)
            return False

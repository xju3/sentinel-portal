"""
Diagnosis service - business logic for patrol diagnosis record operations
"""

import logging
import time
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pub.manager.database import db_manager
from pub.models.diagnosis import DiagnosisRecord, DiagnosisResult, DiagnosisResultItem
from pub.models.sensor import PatrolDiagnosticRecord, Sensor, SensorMonitoring

logger = logging.getLogger(__name__)

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

        try:
            await db_manager.ensure_schema()
            async with db_manager.SessionLocal() as session:
                relation_ids = _diagnosis_relation_ids(context)
                
                quality_status = _parse_quality_status(payload.get("quality"))
                
                # If quality is unusable, immediately terminate the workflow state
                initial_status = "COMPLETED" if quality_status == 1 else "PROCESSING"
                initial_level = "严重" if quality_status == 1 else None
                initial_anomaly = True if quality_status == 1 else False

                record = DiagnosisRecord(
                    id=UUID(report_id),
                    sn=sn,
                    report_ts=report_ts,
                    schema_version=payload.get("schema_version"),
                    sample_type=payload.get("sample_type"),
                    temperature_c=payload.get("temperature_c"),
                    fs_hz=payload.get("fs_hz"),
                    requested_range_g=payload.get("requested_range_g"),
                    range_g=payload.get("range_g"),
                    points=payload.get("points"),
                    duration_ms=payload.get("duration_ms"),
                    task_id=payload.get("task_id"),
                    quality_status=quality_status,
                    quality_attempts=payload.get("quality", {}).get("attempts") if isinstance(payload.get("quality"), dict) else None,
                    status=initial_status,
                    overall_level=initial_level,
                    is_anomaly=initial_anomaly,
                    **relation_ids,
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
        status: str,
        overall_level: str | None = None,
        is_anomaly: bool = False,
    ) -> bool:
        """Update the status of an existing DiagnosisRecord."""
        if db_manager.SessionLocal is None:
            return False
            
        try:
            async with db_manager.SessionLocal() as session:
                stmt = select(DiagnosisRecord).where(DiagnosisRecord.id == UUID(report_id))
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()
                if record:
                    record.status = status
                    if overall_level is not None:
                        record.overall_level = overall_level
                    record.is_anomaly = is_anomaly
                    await session.commit()
                    return True
                return False
        except Exception as e:
            logger.error("Failed to update diagnosis record status: %s", e)
            return False

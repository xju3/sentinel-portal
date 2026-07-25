"""
Diagnosis service - business logic for patrol diagnosis record operations
"""

import logging
from typing import Any, Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pub.manager.database import db_manager
from pub.models.diagnosis import Diagnosis

logger = logging.getLogger(__name__)

def _parse_quality_status(quality: Any) -> int:
    """Parse the raw quality object to determine the integer quality_status (0=usable, 1=unusable)."""
    if not isinstance(quality, dict):
        return 1
    status = quality.get("status")
    if status == 0 or status == "ok":
        return 0
    return 1

class DiagnosisRecordService:
    """Service for managing the parent Diagnosis."""

    @staticmethod
    async def create_managed(
        report_id: str,
        sn: str,
        report_ts: int,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> Optional[Diagnosis]:
        """Create a new Diagnosis using an internally managed session."""
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
                location_id = monitoring.get("location_id")
                
                if not device_id or not location_id:
                    logger.warning(f"Missing device_id or location_id for sn {sn}, skipping diagnosis record creation.")
                    return None

                quality_status = _parse_quality_status(payload.get("quality"))
                
                # If quality is unusable (1), we might consider it as level 4 (Critical) or just skip
                initial_level = 4 if quality_status == 1 else 0
                
                diagnosed_at = datetime.fromtimestamp(report_ts / 1000.0) if report_ts else datetime.utcnow()

                record = Diagnosis(
                    id=UUID(report_id) if report_id else None,
                    device_id=UUID(str(device_id)),
                    location_id=UUID(str(location_id)),
                    report_id=report_id,
                    overall_level=initial_level,
                    resampling=0,
                    diagnosed_at=diagnosed_at,
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
        overall_level: int | None = None,
        is_anomaly: bool = False,
    ) -> bool:
        """Update the status of an existing Diagnosis."""
        if db_manager.SessionLocal is None:
            return False
            
        try:
            async with db_manager.SessionLocal() as session:
                stmt = select(Diagnosis).where(Diagnosis.id == UUID(report_id))
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()
                if record:
                    if overall_level is not None:
                        record.overall_level = overall_level
                    await session.commit()
                    return True
                return False
        except Exception as e:
            logger.error("Failed to update diagnosis record status: %s", e)
            return False

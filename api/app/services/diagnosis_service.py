"""
Diagnosis service - business logic for patrol diagnosis record operations
"""

import logging
from datetime import datetime
from typing import Dict, Any

from app.database import db_manager
from app.models.sensor import PatrolDiagnosticRecord

logger = logging.getLogger(__name__)


class PatrolDiagnosisRecordService:
    """Service for managing patrol diagnosis records in the database."""

    @staticmethod
    async def save_record(report: Dict[str, Any]) -> None:
        """Save a diagnosis report to the PatrolDiagnosticRecord table.

        Manages its own database session internally.

        Args:
            report: The diagnosis report dict from PatrolDiagnosticEngine.run_diagnostics().
                    Expected keys: sn, metric, health_status,
                                   comprehensive_conclusion (optional),
                                   diagnostic_details (optional).
        """
        try:
            async with db_manager.SessionLocal() as session:
                record = PatrolDiagnosticRecord(
                    sn=report["sn"],
                    metric=report["metric"],
                    health_status=report["health_status"],
                    conclusion=report.get("comprehensive_conclusion"),
                    details=report.get("diagnostic_details"),
                    ts=datetime.utcnow(),
                )
                session.add(record)
                await session.commit()
                logger.info(
                    f"Diagnosis record saved: SN={record.sn}, "
                    f"metric={record.metric}, status={record.health_status}"
                )
        except Exception as e:
            logger.error(f"Failed to save diagnosis record: {e}")

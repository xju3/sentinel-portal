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
                    ts=int(time.time() * 1000),  # Unix毫秒时间戳
                )
                session.add(record)
                await session.commit()
                logger.info(
                    f"Diagnosis record saved: SN={record.sn}, "
                    f"metric={record.metric}, status={record.health_status}"
                )
        except Exception as e:
            logger.error(f"Failed to save diagnosis record: {e}")

    @staticmethod
    async def update_sensor_status(sn: str, anomaly_code: int) -> None:
        """Update SensorMonitoring anomaly status by sensor SN.

        Looks up the Sensor by SN, then updates the corresponding
        SensorMonitoring record's anomaly field.

        Args:
            sn: The sensor serial number.
            anomaly_code: 0=normal, 1=rms anomaly, 2=temperature anomaly, 3=both.
        """
        try:
            async with db_manager.SessionLocal() as session:
                # 1. Find Sensor by SN
                sensor_stmt = select(Sensor).where(Sensor.sn == sn).limit(1)
                sensor_result = await session.execute(sensor_stmt)
                sensor = sensor_result.scalar_one_or_none()

                if not sensor:
                    logger.warning(f"Sensor not found for SN={sn}, skipping anomaly update")
                    return

                # 2. Find SensorMonitoring by sensor_id
                monitor_stmt = (
                    select(SensorMonitoring)
                    .where(
                        SensorMonitoring.sensor_id == sensor.id,
                        SensorMonitoring.status == 1,
                    )
                    .limit(1)
                )
                monitor_result = await session.execute(monitor_stmt)
                monitor = monitor_result.scalar_one_or_none()

                if not monitor:
                    logger.warning(
                        f"SensorMonitoring not found for sensor_id={sensor.id} (SN={sn}), "
                        f"skipping anomaly update"
                    )
                    return

                # 3. Update anomaly and ts
                old_anomaly = monitor.anomaly
                monitor.anomaly = anomaly_code

                # 如果之前正常(0)现在有异常(≠0)，记录异常时间
                if old_anomaly == 0 and anomaly_code != 0:
                    monitor.ts = int(time.time() * 1000)
                # 如果之前有异常现在恢复正常，清空异常时间
                elif old_anomaly != 0 and anomaly_code == 0:
                    monitor.ts = None
                # 其他情况（异常→异常，正常→正常）不更新 ts

                await session.commit()
                logger.info(
                    f"SensorMonitoring anomaly updated: sensor_id={sensor.id}, "
                    f"SN={sn}, anomaly={anomaly_code}"
                )

        except Exception as e:
            logger.error(f"Failed to update sensor status for SN={sn}: {e}")

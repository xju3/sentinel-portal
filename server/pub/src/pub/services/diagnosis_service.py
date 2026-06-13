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

from pub.database import db_manager
from pub.models.diagnosis import DiagnosisResult, DiagnosisResultItem
from pub.models.sensor import PatrolDiagnosticRecord, Sensor, SensorMonitoring

logger = logging.getLogger(__name__)


class DiagnosisResultService:
    """Service for storing and querying structured diagnosis results."""

    @staticmethod
    async def create(
        session: AsyncSession,
        data: dict[str, Any],
        items: list[dict[str, Any]] | None = None,
    ) -> DiagnosisResult:
        """Create a diagnosis result with optional per-check items."""
        data = dict(data)
        item_data = items or data.pop("items", None) or []
        db_obj = DiagnosisResult(**data)
        session.add(db_obj)
        await session.flush()

        if item_data:
            session.add_all(
                [
                    DiagnosisResultItem(
                        result_id=db_obj.id,
                        sort_order=index,
                        **item,
                    )
                    for index, item in enumerate(item_data)
                ]
            )

        await session.commit()
        await session.refresh(db_obj)
        return await DiagnosisResultService.get_by_id(session, db_obj.id) or db_obj

    @staticmethod
    async def get_by_id(session: AsyncSession, result_id: UUID) -> Optional[DiagnosisResult]:
        stmt = (
            select(DiagnosisResult)
            .options(selectinload(DiagnosisResult.items))
            .where(DiagnosisResult.id == result_id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_report_id(
        session: AsyncSession,
        report_id: str,
        metric: str | None = None,
    ) -> list[DiagnosisResult]:
        stmt = (
            select(DiagnosisResult)
            .options(selectinload(DiagnosisResult.items))
            .where(DiagnosisResult.report_id == report_id)
            .order_by(desc(DiagnosisResult.diagnosed_at))
        )
        if metric:
            stmt = stmt.where(DiagnosisResult.metric == metric)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_by_sn(
        session: AsyncSession,
        sn: str,
        metric: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[DiagnosisResult]:
        stmt = (
            select(DiagnosisResult)
            .options(selectinload(DiagnosisResult.items))
            .where(DiagnosisResult.sn == sn)
            .order_by(desc(DiagnosisResult.report_ts), desc(DiagnosisResult.diagnosed_at))
            .offset(skip)
            .limit(limit)
        )
        if metric:
            stmt = stmt.where(DiagnosisResult.metric == metric)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_latest_by_sn(
        session: AsyncSession,
        sn: str,
        metric: str | None = None,
    ) -> Optional[DiagnosisResult]:
        results = await DiagnosisResultService.list_by_sn(
            session=session,
            sn=sn,
            metric=metric,
            skip=0,
            limit=1,
        )
        return results[0] if results else None

    @staticmethod
    async def save_temperature_result(
        session: AsyncSession,
        result: Any,
        report_ts: int | None = None,
    ) -> DiagnosisResult:
        """Persist a temperature diagnosis result object.

        The object is intentionally duck-typed so the shared `pub` package does
        not need to import DIA's temperature dataclasses.
        """
        data, items = DiagnosisResultService.metric_result_to_record_data(
            result,
            metric="temperature",
            report_ts=report_ts,
        )
        return await DiagnosisResultService.create(session, data, items)

    @staticmethod
    async def save_metric_result(
        session: AsyncSession,
        result: Any,
        report_ts: int | None = None,
    ) -> DiagnosisResult:
        """Persist a structured diagnosis result object with a `metric` attribute."""
        data, items = DiagnosisResultService.metric_result_to_record_data(
            result,
            report_ts=report_ts,
        )
        return await DiagnosisResultService.create(session, data, items)

    @staticmethod
    async def save_metric_result_managed(
        result: Any,
        report_ts: int | None = None,
    ) -> Optional[DiagnosisResult]:
        """Persist a structured diagnosis result using an internally managed session."""
        if db_manager.SessionLocal is None:
            raise RuntimeError("Database not initialized. Call db_manager.init() first.")

        try:
            await db_manager.ensure_schema()
            async with db_manager.SessionLocal() as session:
                return await DiagnosisResultService.save_metric_result(
                    session=session,
                    result=result,
                    report_ts=report_ts,
                )
        except Exception as e:
            logger.error("Failed to save diagnosis result: %s", e)
            return None

    @staticmethod
    async def save_temperature_result_managed(
        result: Any,
        report_ts: int | None = None,
    ) -> Optional[DiagnosisResult]:
        """Persist a temperature diagnosis result using an internally managed session."""
        if db_manager.SessionLocal is None:
            raise RuntimeError("Database not initialized. Call db_manager.init() first.")

        try:
            await db_manager.ensure_schema()
            async with db_manager.SessionLocal() as session:
                return await DiagnosisResultService.save_temperature_result(
                    session=session,
                    result=result,
                    report_ts=report_ts,
                )
        except Exception as e:
            logger.error("Failed to save temperature diagnosis result: %s", e)
            return None

    @staticmethod
    def temperature_result_to_record_data(
        result: Any,
        report_ts: int | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        return DiagnosisResultService.metric_result_to_record_data(
            result,
            metric="temperature",
            report_ts=report_ts,
        )

    @staticmethod
    def metric_result_to_record_data(
        result: Any,
        metric: str | None = None,
        report_ts: int | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        conclusion = result.conclusion
        data = {
            "report_id": result.report_id,
            "sn": result.sn,
            "metric": metric or result.metric,
            "level": conclusion.level,
            "triggered": bool(conclusion.triggered),
            "conclusion": conclusion.conclusion,
            "evidence": _json_safe(conclusion.evidence),
            "report_ts": report_ts,
        }
        items = [
            {
                "name": item.name,
                "level": item.level,
                "triggered": bool(item.triggered),
                "conclusion": item.conclusion,
                "evidence": _json_safe(item.evidence),
            }
            for item in conclusion.items
        ]
        return data, items


def _json_safe(value: Any) -> Any:
    """Return a JSON-column friendly value."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)


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
                    .where(SensorMonitoring.sensor_id == sensor.id)
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

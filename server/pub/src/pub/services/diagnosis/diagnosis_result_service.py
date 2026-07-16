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
            .where(DiagnosisResult.report_id == UUID(report_id))
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
        context: dict[str, Any] | None = None,
    ) -> DiagnosisResult:
        """Persist a temperature diagnosis result object.

        The object is intentionally duck-typed so the shared `pub` package does
        not need to import DIA's temperature dataclasses.
        """
        data, items = DiagnosisResultService.metric_result_to_record_data(
            result,
            metric="temperature",
            report_ts=report_ts,
            context=context,
        )
        return await DiagnosisResultService.create(session, data, items)

    @staticmethod
    async def save_metric_result(
        session: AsyncSession,
        result: Any,
        report_ts: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> DiagnosisResult:
        """Persist a structured diagnosis result object with a `metric` attribute."""
        data, items = DiagnosisResultService.metric_result_to_record_data(
            result,
            report_ts=report_ts,
            context=context,
        )
        return await DiagnosisResultService.create(session, data, items)

    @staticmethod
    async def save_metric_result_managed(
        result: Any,
        report_ts: int | None = None,
        context: dict[str, Any] | None = None,
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
                    context=context,
                )
        except Exception as e:
            logger.error("Failed to save diagnosis result: %s", e)
            return None

    @staticmethod
    async def save_temperature_result_managed(
        result: Any,
        report_ts: int | None = None,
        context: dict[str, Any] | None = None,
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
                    context=context,
                )
        except Exception as e:
            logger.error("Failed to save temperature diagnosis result: %s", e)
            return None

    @staticmethod
    def temperature_result_to_record_data(
        result: Any,
        report_ts: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        return DiagnosisResultService.metric_result_to_record_data(
            result,
            metric="temperature",
            report_ts=report_ts,
            context=context,
        )

    @staticmethod
    def metric_result_to_record_data(
        result: Any,
        metric: str | None = None,
        report_ts: int | None = None,
        context: dict[str, Any] | None = None,
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


def _parse_quality_status(quality: Any) -> int:
    """Parse the raw quality object to determine the integer quality_status (0=usable, 1=unusable)."""
    if not isinstance(quality, dict):
        return 1
    status = quality.get("status")
    if status == 0 or status == "ok":
        return 0
    return 1


def _diagnosis_relation_ids(context: dict[str, Any] | None) -> dict[str, Any]:
    """Extract relational IDs from cached diagnosis context."""
    if not isinstance(context, dict):
        return {}

    sensor = context.get("sensor") if isinstance(context.get("sensor"), dict) else {}
    monitoring = context.get("monitoring") if isinstance(context.get("monitoring"), dict) else {}
    device_inst = context.get("device_inst") if isinstance(context.get("device_inst"), dict) else {}
    device_spec = context.get("device_spec") if isinstance(context.get("device_spec"), dict) else {}
    device_category = context.get("device_category") if isinstance(context.get("device_category"), dict) else {}

    relation_ids = {
        "sensor_id": sensor.get("id"),
        "sensor_monitoring_id": monitoring.get("id"),
        "device_inst_id": device_inst.get("id") or monitoring.get("device_inst_id"),
        "device_spec_id": device_spec.get("id") or device_inst.get("device_spec_id"),
        "device_category_id": device_category.get("id") or device_spec.get("device_category_id"),
    }
    return {field: _optional_uuid(value, field) for field, value in relation_ids.items()}


def _optional_uuid(value: Any, field: str) -> UUID | None:
    """Convert a cached relation ID to the UUID type expected by SQLAlchemy."""
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid diagnosis context UUID for {field}: {value!r}") from exc

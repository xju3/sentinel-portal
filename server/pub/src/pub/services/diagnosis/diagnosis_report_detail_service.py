from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pub.models.customer import Location
from pub.models.device import (
    DeviceCategory,
    DeviceInst,
    DeviceSpec,
    Process,
    ProcessDevice,
    ProcessDeviceItem,
)
from pub.models.diagnosis import (
    Diagnosis,
    DiagnosisCase,
    DiagnosisCaseAttempt,
    DiagnosisItem,
    DiagnosisRecord,
    DiagnosisRecordStatus,
)
LEVEL_LABELS = {
    0: "正常",
    1: "关注",
    2: "异常",
    3: "告警",
    4: "危险",
}
FAULT_LABELS = {
    "temperature": "温度",
    "vibration": "振动",
    "bearing_bpfo": "轴承外圈",
    "bearing_bpfi": "轴承内圈",
    "bearing_bsf": "轴承滚动体",
    "bearing_ftf": "轴承保持架",
    "legacy_aggregate": "历史记录",
}
REPORT_STATUS_LABELS = {
    int(DiagnosisRecordStatus.RECEIVED): "RECEIVED",
    int(DiagnosisRecordStatus.WAITING): "WAITING",
    int(DiagnosisRecordStatus.DIAGNOSED): "DIAGNOSED",
    int(DiagnosisRecordStatus.SKIPPED): "SKIPPED",
    int(DiagnosisRecordStatus.MISSED): "MISSED",
}


@dataclass(slots=True)
class DiagnosisReportBundle:
    report: DiagnosisRecord
    diagnosis: Diagnosis | None
    items: list[DiagnosisItem]
    cases: list[DiagnosisCase]
    attempts: list[DiagnosisCaseAttempt]
    temperature_trend: list[DiagnosisRecord]
    device: DeviceInst | None
    device_spec: DeviceSpec | None
    device_category: DeviceCategory | None
    process_device: ProcessDevice | None
    process: Process | None
    location: Location | None


class DiagnosisReportDetailService:
    """Aggregate one diagnosis report into the detail payload consumed by portal/Wx."""

    @classmethod
    async def get_portal_detail(
        cls,
        *,
        session: AsyncSession,
        report_id: UUID,
        tenant_id: UUID,
    ) -> dict[str, Any]:
        bundle = await cls._load_bundle(session=session, report_id=report_id)
        if bundle.report.tenant_id != tenant_id:
            raise PermissionError("diagnosis report is not owned by current tenant")
        return cls._build_payload(bundle)

    @classmethod
    async def get_report_detail(
        cls,
        *,
        session: AsyncSession,
        report_id: UUID,
        fault_type: str | None = None,
    ) -> dict[str, Any]:
        bundle = await cls._load_bundle(session=session, report_id=report_id)
        payload = cls._build_payload(bundle)
        if fault_type is not None:
            payload["faults"] = [
                fault
                for fault in payload["faults"]
                if fault["fault_type"] == fault_type
            ]
            levels = [
                fault["level"]
                for fault in payload["faults"]
                if isinstance(fault.get("level"), int)
            ]
            scoped_level = max(levels) if levels else None
            payload["report"]["overall_level"] = scoped_level
            payload["report"]["overall_label"] = (
                LEVEL_LABELS.get(scoped_level, "未形成诊断")
            )
            payload["provenance"] = cls._build_provenance(payload["faults"])
        return payload

    @classmethod
    async def _load_bundle(
        cls,
        *,
        session: AsyncSession,
        report_id: UUID,
    ) -> DiagnosisReportBundle:
        report = await session.get(DiagnosisRecord, report_id)
        if report is None:
            raise LookupError("diagnosis report not found")

        diagnosis = await cls._load_diagnosis(session=session, report_id=report_id)
        items = await cls._load_items(
            session=session,
            diagnosis_id=diagnosis.id if diagnosis is not None else None,
        )
        cases = await cls._load_cases(session=session, report_id=report_id)
        attempts = await cls._load_attempts(session=session, cases=cases)
        temperature_trend = await cls._load_temperature_trend(
            session=session,
            report=report,
        )
        device = await session.get(DeviceInst, report.device_id) if report.device_id else None
        device_spec = (
            await session.get(DeviceSpec, device.device_spec_id)
            if device is not None
            else None
        )
        device_category_id = report.device_category_id or (
            device_spec.device_category_id if device_spec is not None else None
        )
        device_category = (
            await session.get(DeviceCategory, device_category_id)
            if device_category_id
            else None
        )
        process_device = await cls._load_process_device(
            session=session,
            report=report,
            device=device,
        )
        process = (
            await session.get(Process, process_device.process_id)
            if process_device is not None
            else None
        )
        location = await session.get(Location, report.location_id) if report.location_id else None
        return DiagnosisReportBundle(
            report=report,
            diagnosis=diagnosis,
            items=items,
            cases=cases,
            attempts=attempts,
            temperature_trend=temperature_trend,
            device=device,
            device_spec=device_spec,
            device_category=device_category,
            process_device=process_device,
            process=process,
            location=location,
        )

    @staticmethod
    async def _load_diagnosis(
        *,
        session: AsyncSession,
        report_id: UUID,
    ) -> Diagnosis | None:
        result = await session.execute(
            select(Diagnosis)
            .where(
                or_(
                    Diagnosis.report_uuid == report_id,
                    Diagnosis.report_id == str(report_id),
                )
            )
            .order_by(desc(Diagnosis.created_at))
        )
        return result.scalars().first()

    @staticmethod
    async def _load_items(
        *,
        session: AsyncSession,
        diagnosis_id: UUID | None,
    ) -> list[DiagnosisItem]:
        if diagnosis_id is None:
            return []
        result = await session.execute(
            select(DiagnosisItem)
            .where(DiagnosisItem.diagnosis_id == diagnosis_id)
            .order_by(desc(DiagnosisItem.level), DiagnosisItem.created_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def _load_temperature_trend(
        *,
        session: AsyncSession,
        report: DiagnosisRecord,
    ) -> list[DiagnosisRecord]:
        if report.device_id is None or report.ts_ms is None:
            return []
        window_start_ms = int(report.ts_ms) - 72 * 60 * 60 * 1000
        result = await session.execute(
            select(DiagnosisRecord)
            .where(
                DiagnosisRecord.device_id == report.device_id,
                DiagnosisRecord.ts_ms >= window_start_ms,
                DiagnosisRecord.ts_ms <= int(report.ts_ms),
                DiagnosisRecord.temperature_c.is_not(None),
            )
            .order_by(DiagnosisRecord.ts_ms)
        )
        return list(result.scalars().all())

    @staticmethod
    async def _load_cases(
        *,
        session: AsyncSession,
        report_id: UUID,
    ) -> list[DiagnosisCase]:
        result = await session.execute(
            select(DiagnosisCase)
            .where(DiagnosisCase.root_report_id == report_id)
            .order_by(DiagnosisCase.created_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def _load_attempts(
        *,
        session: AsyncSession,
        cases: list[DiagnosisCase],
    ) -> list[DiagnosisCaseAttempt]:
        case_ids = [case.id for case in cases]
        if not case_ids:
            return []
        result = await session.execute(
            select(DiagnosisCaseAttempt)
            .where(DiagnosisCaseAttempt.case_id.in_(case_ids))
            .order_by(
                DiagnosisCaseAttempt.case_id,
                DiagnosisCaseAttempt.sequence,
                DiagnosisCaseAttempt.created_at,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def _load_process_device(
        *,
        session: AsyncSession,
        report: DiagnosisRecord,
        device: DeviceInst | None,
    ) -> ProcessDevice | None:
        if report.process_device_id:
            return await session.get(ProcessDevice, report.process_device_id)
        if device is None:
            return None
        result = await session.execute(
            select(ProcessDevice)
            .join(ProcessDeviceItem, ProcessDeviceItem.process_device_id == ProcessDevice.id)
            .where(ProcessDeviceItem.device_inst_id == device.id)
            .order_by(ProcessDevice.id)
        )
        return result.scalars().first()

    @classmethod
    def _build_payload(cls, bundle: DiagnosisReportBundle) -> dict[str, Any]:
        grouped_items: dict[str, list[DiagnosisItem]] = {}
        for item in bundle.items:
            fault_type = cls._item_fault_type(item)
            grouped_items.setdefault(fault_type, []).append(item)

        case_by_fault = {case.fault_type: case for case in bundle.cases}
        attempt_groups: dict[UUID, list[DiagnosisCaseAttempt]] = {}
        for attempt in bundle.attempts:
            attempt_groups.setdefault(attempt.case_id, []).append(attempt)
        fault_types = sorted(set(grouped_items) | set(case_by_fault))
        faults = [
            cls._build_fault_detail(
                fault_type=fault_type,
                items=grouped_items.get(fault_type, []),
                case=case_by_fault.get(fault_type),
                attempts=attempt_groups.get(case_by_fault[fault_type].id, [])
                if case_by_fault.get(fault_type)
                else [],
                temperature_trend=(
                    bundle.temperature_trend
                    if fault_type == "temperature"
                    else []
                ),
            )
            for fault_type in fault_types
        ]

        report_diagnosed_at = bundle.report.diagnosed_at or (
            bundle.diagnosis.diagnosed_at if bundle.diagnosis is not None else None
        )
        sampled_at = _ts_ms_to_iso(bundle.report.ts_ms)
        return {
            "report": {
                "report_id": str(bundle.report.id),
                "diagnosed_at": _dt_to_iso(report_diagnosed_at),
                "sampled_at": sampled_at,
                "overall_level": bundle.report.overall_level,
                "overall_label": LEVEL_LABELS.get(bundle.report.overall_level, "未形成诊断"),
                "diagnosis_status": int(bundle.report.diagnosis_status),
                "diagnosis_status_label": REPORT_STATUS_LABELS.get(
                    int(bundle.report.diagnosis_status),
                    "UNKNOWN",
                ),
            },
            "device": {
                "id": str(bundle.device.id) if bundle.device is not None else None,
                "code": bundle.device.code if bundle.device is not None else None,
                "name": bundle.device.name if bundle.device is not None else None,
                "category": (
                    bundle.device_category.name if bundle.device_category is not None else None
                ),
                "process": bundle.process.name if bundle.process is not None else None,
                "location": bundle.location.name if bundle.location is not None else None,
                "sensor_sn": bundle.report.sensor_sn,
            },
            "faults": faults,
            "provenance": cls._build_provenance(faults),
        }

    @classmethod
    def _build_fault_detail(
        cls,
        *,
        fault_type: str,
        items: list[DiagnosisItem],
        case: DiagnosisCase | None,
        attempts: list[DiagnosisCaseAttempt],
        temperature_trend: list[DiagnosisRecord],
    ) -> dict[str, Any]:
        primary_item = (
            max(items, key=lambda item: int(item.level or 0))
            if items
            else None
        )
        evidence = (
            primary_item.evidence if isinstance(getattr(primary_item, "evidence", None), dict) else {}
        )
        evidence_schema_version = _as_int(evidence.get("schema_version"))
        level = cls._fault_level(primary_item=primary_item, attempts=attempts)
        return {
            "case_id": str(case.id) if case is not None else None,
            "fault_type": fault_type,
            "fault_label": FAULT_LABELS.get(fault_type, fault_type),
            "level": level,
            "level_label": LEVEL_LABELS.get(level, "未知"),
            "summary": cls._fault_summary(primary_item, items, attempts),
            "evidence_schema_version": evidence_schema_version,
            "checks": cls._collect_checks(items),
            "context": evidence.get("context") if evidence else None,
            "confirmation_status": (
                case.confirmation_status if case is not None else evidence.get("confirmation_status")
            ),
            "attempts": [cls._build_attempt_payload(attempt) for attempt in attempts],
            "trend": cls._build_temperature_trend_payload(
                primary_item=primary_item,
                evidence_schema_version=evidence_schema_version,
                records=temperature_trend,
            ),
        }

    @classmethod
    def _build_temperature_trend_payload(
        cls,
        *,
        primary_item: DiagnosisItem | None,
        evidence_schema_version: int | None,
        records: list[DiagnosisRecord],
    ) -> dict[str, Any]:
        status = cls._trend_status(primary_item, evidence_schema_version)
        if not records:
            return {"status": status, "series": []}
        return {
            "status": status,
            "series": [
                {
                    "key": "temperature_72h",
                    "label": "72小时温度",
                    "unit": "°C",
                    "points": [
                        {
                            "sampled_at": _ts_ms_to_iso(record.ts_ms),
                            "value": record.temperature_c,
                        }
                        for record in records
                    ],
                }
            ],
        }

    @staticmethod
    def _fault_level(
        *,
        primary_item: DiagnosisItem | None,
        attempts: list[DiagnosisCaseAttempt],
    ) -> int | None:
        if primary_item is not None:
            return int(primary_item.level)
        for attempt in reversed(attempts):
            if attempt.fault_level is not None:
                return int(attempt.fault_level)
        return None

    @staticmethod
    def _fault_summary(
        primary_item: DiagnosisItem | None,
        items: list[DiagnosisItem],
        attempts: list[DiagnosisCaseAttempt],
    ) -> str | None:
        if primary_item is not None and primary_item.description:
            return primary_item.description
        for item in items:
            evidence = item.evidence if isinstance(item.evidence, dict) else {}
            result = evidence.get("result")
            if isinstance(result, dict):
                primary_rule = result.get("primary_rule")
                if isinstance(primary_rule, str) and primary_rule:
                    return primary_rule
        for attempt in reversed(attempts):
            if attempt.description:
                return attempt.description
        return None

    @staticmethod
    def _collect_checks(items: list[DiagnosisItem]) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        for item in items:
            evidence = item.evidence if isinstance(item.evidence, dict) else {}
            item_checks = evidence.get("checks")
            if isinstance(item_checks, list):
                for check in item_checks:
                    if isinstance(check, dict):
                        checks.append(check)
        return checks

    @staticmethod
    def _build_attempt_payload(attempt: DiagnosisCaseAttempt) -> dict[str, Any]:
        evidence = attempt.evidence if isinstance(attempt.evidence, dict) else {}
        evidence_schema_version = _as_int(evidence.get("schema_version"))
        return {
            "attempt_id": str(attempt.id),
            "report_id": str(attempt.report_id),
            "phase": attempt.phase,
            "sequence": attempt.sequence,
            "result_status": attempt.result_status,
            "level": attempt.fault_level,
            "level_label": LEVEL_LABELS.get(attempt.fault_level, "未知"),
            "description": attempt.description,
            "diagnosed_at": _dt_to_iso(attempt.diagnosed_at),
            "evidence_schema_version": evidence_schema_version,
            "evidence_status": (
                "complete"
                if evidence_schema_version and evidence_schema_version >= 2
                else "legacy_partial"
            )
            if evidence
            else "unavailable",
            "rms": evidence.get("current"),
            "confirmation_status": evidence.get("confirmation_status"),
            "evidence": evidence or None,
        }

    @staticmethod
    def _trend_status(
        primary_item: DiagnosisItem | None,
        evidence_schema_version: int | None,
    ) -> str:
        if primary_item is None:
            return "unavailable"
        if evidence_schema_version is None:
            return "legacy_partial" if primary_item.evidence else "unavailable"
        return "complete" if evidence_schema_version >= 2 else "legacy_partial"

    @staticmethod
    def _build_provenance(faults: list[dict[str, Any]]) -> dict[str, str]:
        has_structured_thresholds = any(
            isinstance(fault.get("evidence_schema_version"), int)
            and fault["evidence_schema_version"] >= 2
            for fault in faults
        )
        return {
            "thresholds": "diagnosis_snapshot" if has_structured_thresholds else "legacy_partial",
            "trend_series": (
                "diagnosis_record"
                if any(
                    isinstance(fault.get("trend"), dict)
                    and fault["trend"].get("series")
                    for fault in faults
                )
                else "unavailable"
            ),
        }

    @staticmethod
    def _item_fault_type(item: DiagnosisItem) -> str:
        if item.fault_type in {
            "temperature",
            "vibration",
            "bearing_bpfo",
            "bearing_bpfi",
            "bearing_bsf",
            "bearing_ftf",
            "legacy_aggregate",
        }:
            return str(item.fault_type)
        if item.metric_id == 0:
            return "temperature"
        return "vibration"


def _dt_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _ts_ms_to_iso(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    return None

"""
Sensor task generation helpers.

This module owns task action rules and completion paths.

Encoding rules:
- action=0: firmware upgrade, completed by the device callback API.
- action=1: config update, completed by the device callback API.
- action=2: device status report, completed with the status upload.
- action=3: update binding info, triggering the device to fetch binding status.
- action 11..98: default-parameter dense collection, encoded as T I.
  T = focus type, I = interval minutes, val = repeat count.
  Focus types: 1=general, 2=temperature, 3=RMS, 4=impact/spectrum.
  Example: action=15, val=3 -> collect full data every 5 minutes, repeat 3
  times.
  Example: action=25, val=3 -> collect full data every 5 minutes, repeat 3
  times with temperature as the server-side review focus.
- action=99: FFT collection. The device chooses FFT size and range locally.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pub.manager.database import db_manager
from pub.models.diagnosis import DiagnosisRecord
from pub.models.sensor import (
    DeviceFftRecord,
    Sensor,
    SensorBatch,
    SensorMonitoring,
    SensorStatus,
    SensorTask,
    SensorTaskReport,
)
from pub.services.sensor.firmware_cache_service import SensorOTAContextService

SENSOR_TASK_STATUS_PENDING = 0
SENSOR_TASK_STATUS_DONE = 1
SENSOR_TASK_STATUS_DISPATCHED = 2
SENSOR_TASK_STATUS_FAILED = 3
SENSOR_TASK_OPEN_STATUSES = (SENSOR_TASK_STATUS_PENDING, SENSOR_TASK_STATUS_DISPATCHED)
SYSTEM_ACTION_FIRMWARE_UPGRADE = 0
SYSTEM_ACTION_CONFIG_UPDATE = 1
SYSTEM_ACTION_STATUS_REPORT = 2
SYSTEM_ACTION_UPDATE_BINDING = 3
SYSTEM_ACTIONS_COMPLETED_BY_CALLBACK = (
    SYSTEM_ACTION_FIRMWARE_UPGRADE,
    SYSTEM_ACTION_CONFIG_UPDATE,
    SYSTEM_ACTION_UPDATE_BINDING,
)

DEFAULT_DENSE_MIN_INTERVAL_MIN = 1
DEFAULT_DENSE_MAX_INTERVAL_MIN = 9
DEFAULT_DENSE_FOCUS_GENERAL = 1
DEFAULT_DENSE_FOCUS_TEMPERATURE = 2
DEFAULT_DENSE_FOCUS_RMS = 3
DEFAULT_DENSE_FOCUS_IMPACT_SPECTRUM = 4
DEFAULT_DENSE_FOCUS_LABELS = {
    DEFAULT_DENSE_FOCUS_GENERAL: "综合复核",
    DEFAULT_DENSE_FOCUS_TEMPERATURE: "温度复核",
    DEFAULT_DENSE_FOCUS_RMS: "RMS复核",
    DEFAULT_DENSE_FOCUS_IMPACT_SPECTRUM: "冲击/频谱复核",
}
FFT_COLLECTION_ACTION = 99
RESAMPLING_ACTION = 53
RESAMPLING_REPEAT_COUNT = 3
DAILY_FFT_INTERVAL = timedelta(hours=24)

TASK_PURPOSE_RESAMPLING = "RESAMPLING"
TASK_PURPOSE_FFT_DAILY = "FFT_DAILY"
TASK_PURPOSE_FFT_DIAGNOSIS = "FFT_DIAGNOSIS"

MIN_REPEAT_COUNT = 1

TaskKind = Literal[
    "default_dense_collection",
    "resampling",
    "fft_collection",
]


@dataclass(frozen=True)
class SensorTaskSpec:
    action: int
    val: int
    kind: TaskKind
    description: str


def build_default_dense_collection_spec(
    *,
    interval_minutes: int,
    repeat_count: int,
    focus_type: int = DEFAULT_DENSE_FOCUS_GENERAL,
) -> SensorTaskSpec:
    """Build action/val for full-data dense collection with default parameters."""
    _require_default_dense_focus(focus_type)
    _require_int_range(
        "interval_minutes",
        interval_minutes,
        DEFAULT_DENSE_MIN_INTERVAL_MIN,
        DEFAULT_DENSE_MAX_INTERVAL_MIN,
    )
    _require_repeat_count(repeat_count)
    action = focus_type * 10 + interval_minutes
    focus_label = DEFAULT_DENSE_FOCUS_LABELS[focus_type]
    return SensorTaskSpec(
        action=action,
        val=repeat_count,
        kind="default_dense_collection",
        description=(
            f"默认参数密集采集：重点={focus_label}，每 {interval_minutes} "
            f"分钟采集一次完整数据，重复 {repeat_count} 次"
        ),
    )


def build_fft_collection_spec() -> SensorTaskSpec:
    """Build the parameter-free FFT collection command understood by devices."""
    return SensorTaskSpec(
        action=FFT_COLLECTION_ACTION,
        val=0,
        kind="fft_collection",
        description=(
            "FFT 采集：设备根据转速和至少 20 圈采样要求自动决定点数，"
            "并根据削峰情况自动选择量程"
        ),
    )


def build_resampling_spec() -> SensorTaskSpec:
    """Build the fixed three-pass vibration confirmation task."""
    return SensorTaskSpec(
        action=RESAMPLING_ACTION,
        val=RESAMPLING_REPEAT_COUNT,
        kind="resampling",
        description="振动异常复采：每 5 分钟采集一次完整数据，连续复采 3 次",
    )


def describe_collection_action(action: int, val: int) -> str:
    """Return a human-readable description for a collection task action."""
    if action == FFT_COLLECTION_ACTION:
        return build_fft_collection_spec().description
    if action == RESAMPLING_ACTION and val == RESAMPLING_REPEAT_COUNT:
        return build_resampling_spec().description

    if 10 < action < FFT_COLLECTION_ACTION:
        focus_type = action // 10
        interval = action % 10
        focus_label = DEFAULT_DENSE_FOCUS_LABELS.get(focus_type, f"未知重点({focus_type})")
        return (
            f"默认参数密集采集：重点={focus_label}，每 {interval} "
            f"分钟采集一次完整数据，重复 {val} 次"
        )

    return f"系统任务：action={action}, val={val}"


async def create_collection_task(
    *,
    session: AsyncSession,
    sn: str,
    spec: SensorTaskSpec,
    reason: str,
    name: str | None = None,
    task_purpose: str | None = None,
    commit: bool = True,
) -> SensorTask:
    """Create a pending SensorTask unless an identical pending task exists.

    The task remark deliberately stores both the decoded task content and the
    reason that caused the server to generate it. That makes the compact action
    code auditable when operators inspect the database directly.
    """
    if not sn:
        raise ValueError("sn must be non-empty")
    if not reason:
        raise ValueError("reason must be non-empty")

    existing = await find_equivalent_pending_collection_task(session=session, sn=sn, spec=spec)
    if existing is not None:
        return existing

    dedupe_key = _automatic_task_dedupe_key(sn=sn, spec=spec)
    task = SensorTask(
        name=name or spec.kind,
        sn=sn,
        action=spec.action,
        val=spec.val,
        remark=_task_remark(spec=spec, reason=reason),
        task_purpose=task_purpose,
        dedupe_key=dedupe_key,
        status=SENSOR_TASK_STATUS_PENDING,
        create_time=datetime.utcnow(),
    )
    if commit:
        session.add(task)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            if dedupe_key is None:
                raise
            existing_stmt = select(SensorTask).where(
                SensorTask.dedupe_key == dedupe_key,
                SensorTask.status.in_(SENSOR_TASK_OPEN_STATUSES),
            )
            existing = (await session.execute(existing_stmt)).scalar_one_or_none()
            if existing is None:
                raise
            return existing
        await session.refresh(task)
        return task

    try:
        async with session.begin_nested():
            session.add(task)
            await session.flush()
    except IntegrityError:
        if dedupe_key is None:
            raise
        existing_stmt = select(SensorTask).where(
            SensorTask.dedupe_key == dedupe_key,
            SensorTask.status.in_(SENSOR_TASK_OPEN_STATUSES),
        )
        existing = (await session.execute(existing_stmt)).scalar_one_or_none()
        if existing is None:
            raise
        return existing
    return task


async def list_sensor_tasks(
    *,
    session: AsyncSession,
    current: int,
    page_size: int,
    keyword: str | None = None,
    status: int | None = None,
) -> tuple[list[SensorTask], int]:
    """List tasks for administration without changing delivery state."""
    stmt = select(SensorTask)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        stmt = stmt.where(
            SensorTask.name.ilike(pattern) | SensorTask.sn.ilike(pattern)
        )
    if status is not None:
        stmt = stmt.where(SensorTask.status == status)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int((await session.execute(count_stmt)).scalar_one() or 0)
    tasks = (
        await session.execute(
            stmt.order_by(SensorTask.create_time.desc())
            .offset((current - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(tasks), total


async def create_manual_sensor_task(
    *,
    session: AsyncSession,
    sensor_id: UUID,
    name: str,
    action: int,
    val: int,
    remark: str | None = None,
) -> SensorTask:
    """Create a pending task for a sensor selected by its database id."""
    sensor = await session.get(Sensor, sensor_id)
    if sensor is None:
        raise ValueError("Sensor not found")

    task = SensorTask(
        name=name.strip(),
        sn=sensor.sn,
        action=action,
        val=val,
        remark=remark.strip() if remark else None,
        status=SENSOR_TASK_STATUS_PENDING,
        create_time=datetime.utcnow(),
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def complete_device_system_task(
    *,
    session: AsyncSession,
    task_id: UUID | str,
    success: bool = True,
) -> SensorTask | None:
    """Complete an action 0/1/3 task after the device reports execution result."""
    task = await get_sensor_task_by_id(session, task_id)
    if task is None or task.action not in SYSTEM_ACTIONS_COMPLETED_BY_CALLBACK:
        return None
    target_status = SENSOR_TASK_STATUS_DONE if success else SENSOR_TASK_STATUS_FAILED
    if task.status != target_status:
        if target_status == SENSOR_TASK_STATUS_DONE:
            _mark_sensor_task_done(task)
        else:
            task.status = target_status
            task.dedupe_key = None
        await session.commit()
        await session.refresh(task)
    return task


async def record_sensor_status(
    *,
    session: AsyncSession,
    sn: str,
    ts_ms: int,
    temperature: float | None = None,
    rssi: float | None = None,
    voltage: float | None = None,
    active: bool = True,
    task_id: UUID | str | None = None,
) -> SensorStatus:
    """Persist device status and atomically complete its action=2 task."""
    task = None
    if task_id is not None:
        task = await get_sensor_task_by_id(session, task_id)
        if (
            task is None
            or task.sn != sn
            or task.action != SYSTEM_ACTION_STATUS_REPORT
        ):
            logger.warning(f"Status report included invalid task_id {task_id} for sn {sn}, ignoring task completion.")
            task = None

    status = SensorStatus(
        sn=sn,
        ts=datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).replace(tzinfo=None),
        temperature=temperature,
        rssi=rssi,
        voltage=voltage,
        active=active,
    )
    session.add(status)
    if task is not None and task.status != SENSOR_TASK_STATUS_DONE:
        _mark_sensor_task_done(task)
    await session.commit()
    await session.refresh(status)
    return status


async def create_default_dense_collection_task(
    *,
    session: AsyncSession,
    sn: str,
    interval_minutes: int,
    repeat_count: int,
    reason: str,
    focus_type: int = DEFAULT_DENSE_FOCUS_GENERAL,
) -> SensorTask:
    """Create a default-parameter dense collection task."""
    spec = build_default_dense_collection_spec(
        interval_minutes=interval_minutes,
        repeat_count=repeat_count,
        focus_type=focus_type,
    )
    return await create_collection_task(
        session=session,
        sn=sn,
        spec=spec,
        reason=reason,
        name="default_dense_collection",
    )


async def create_fft_collection_task(
    *,
    session: AsyncSession,
    sn: str,
    reason: str,
    task_purpose: str = TASK_PURPOSE_FFT_DIAGNOSIS,
) -> SensorTask:
    """Create one parameter-free device-managed FFT collection task."""
    return await create_collection_task(
        session=session,
        sn=sn,
        spec=build_fft_collection_spec(),
        reason=reason,
        name="fft_collection",
        task_purpose=task_purpose,
    )


async def create_resampling_task(
    *,
    session: AsyncSession,
    sn: str,
    reason: str,
    commit: bool = True,
) -> SensorTask:
    """Create or reuse the active three-pass vibration resampling task."""
    return await create_collection_task(
        session=session,
        sn=sn,
        spec=build_resampling_spec(),
        reason=reason,
        name="vibration_resampling",
        task_purpose=TASK_PURPOSE_RESAMPLING,
        commit=commit,
    )


async def ensure_resampling_followup_fft_task(
    *,
    session: AsyncSession,
    resampling_task_id: UUID | str,
    reason: str,
    commit: bool = True,
) -> SensorTask | None:
    """Select exactly one FFT follow-up for a completed resampling task.

    The resampling row is locked while its durable follow-up link is assigned.
    An already dispatched FFT may be linked and returned so the API can include
    the same command again when the final resampling upload is retried.
    """
    task_uuid = _parse_task_uuid(resampling_task_id)
    if task_uuid is None:
        return None

    resampling_stmt = (
        select(SensorTask)
        .where(SensorTask.id == task_uuid)
        .with_for_update()
    )
    resampling_task = (
        await session.execute(resampling_stmt)
    ).scalar_one_or_none()
    if (
        resampling_task is None
        or resampling_task.action != RESAMPLING_ACTION
        or int(resampling_task.val or 0) != RESAMPLING_REPEAT_COUNT
    ):
        return None

    if resampling_task.followup_fft_task_id is not None:
        return await get_sensor_task_by_id(
            session,
            resampling_task.followup_fft_task_id,
        )

    open_fft_stmt = (
        select(SensorTask)
        .where(
            SensorTask.sn == resampling_task.sn,
            SensorTask.action == FFT_COLLECTION_ACTION,
            SensorTask.status.in_(SENSOR_TASK_OPEN_STATUSES),
        )
        .order_by(SensorTask.create_time.desc())
        .limit(1)
    )
    fft_task = (await session.execute(open_fft_stmt)).scalar_one_or_none()
    if fft_task is None:
        spec = build_fft_collection_spec()
        dedupe_key = _automatic_task_dedupe_key(
            sn=resampling_task.sn,
            spec=spec,
        )
        fft_task = SensorTask(
            name="fft_collection",
            sn=resampling_task.sn,
            action=spec.action,
            val=spec.val,
            remark=_task_remark(spec=spec, reason=reason),
            task_purpose=TASK_PURPOSE_FFT_DIAGNOSIS,
            dedupe_key=dedupe_key,
            status=SENSOR_TASK_STATUS_PENDING,
            create_time=datetime.utcnow(),
        )
        try:
            async with session.begin_nested():
                session.add(fft_task)
                await session.flush()
        except IntegrityError:
            existing_stmt = select(SensorTask).where(
                SensorTask.dedupe_key == dedupe_key,
                SensorTask.status.in_(SENSOR_TASK_OPEN_STATUSES),
            )
            fft_task = (
                await session.execute(existing_stmt)
            ).scalar_one_or_none()
            if fft_task is None:
                raise
    else:
        fft_task.task_purpose = TASK_PURPOSE_FFT_DIAGNOSIS

    resampling_task.followup_fft_task_id = fft_task.id
    if commit:
        await session.commit()
        await session.refresh(fft_task)
    else:
        await session.flush()
    return fft_task


async def find_open_resampling_task(
    session: AsyncSession,
    sn: str,
) -> SensorTask | None:
    stmt = (
        select(SensorTask)
        .where(
            SensorTask.sn == sn,
            SensorTask.action == RESAMPLING_ACTION,
            SensorTask.val == RESAMPLING_REPEAT_COUNT,
            SensorTask.status.in_(SENSOR_TASK_OPEN_STATUSES),
        )
        .order_by(SensorTask.create_time.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def ensure_daily_fft_task(
    *,
    session: AsyncSession,
    sn: str,
    now: datetime | None = None,
) -> SensorTask | None:
    """Create one daily health FFT when no recent/open FFT or resampling exists."""
    if await find_open_resampling_task(session, sn) is not None:
        return None

    reference_time = now or datetime.utcnow()
    recent_stmt = (
        select(SensorTask)
        .where(
            SensorTask.sn == sn,
            SensorTask.action == FFT_COLLECTION_ACTION,
            SensorTask.status == SENSOR_TASK_STATUS_DONE,
            SensorTask.complete_time.is_not(None),
            SensorTask.complete_time >= reference_time - DAILY_FFT_INTERVAL,
        )
        .order_by(SensorTask.complete_time.desc())
        .limit(1)
    )
    if (await session.execute(recent_stmt)).scalar_one_or_none() is not None:
        return None

    return await create_fft_collection_task(
        session=session,
        sn=sn,
        reason="每日健康巡检：最近 24 小时内没有成功完成的 FFT",
        task_purpose=TASK_PURPOSE_FFT_DAILY,
    )


async def sensor_task_to_device_payload(session: AsyncSession, task: SensorTask) -> dict | None:
    """Serialize a SensorTask in the compact shape expected by ESP32."""
    payload = {
        "id": str(task.id),
        "action": task.action,
        "val": task.val,
    }
    if task.action == SYSTEM_ACTION_FIRMWARE_UPGRADE:
        ctx = await SensorOTAContextService.get_sensor_context(session, task.sn)
        if ctx:
            firmware_info = await SensorOTAContextService.get_active_firmware(
                session=session,
                tenant_id=ctx.get("tenant_id"), 
                sensor_type_id=ctx.get("sensor_type_id")
            )
            if firmware_info:
                presigned_url = SensorOTAContextService.get_cached_presigned_url(
                    firmware_id=firmware_info["id"],
                    file_url=firmware_info["file_url"],
                    version=firmware_info["version"]
                )
                payload["val"] = presigned_url
            else:
                logger.info(f"Skipping firmware task {task.id} for {task.sn}: firmware not active or not found")
                return None
        else:
            logger.warning(f"Skipping firmware task {task.id} for {task.sn}: SN context not found in cache")
            return None
    return payload


async def list_pending_sensor_tasks(session: AsyncSession, sn: str) -> list[SensorTask]:
    """Return pending tasks for one sensor in the same order sent to ESP32."""
    stmt = (
        select(SensorTask)
        .where(SensorTask.sn == sn, SensorTask.status == SENSOR_TASK_STATUS_PENDING)
        .order_by(SensorTask.create_time.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def dispatch_pending_sensor_tasks(session: AsyncSession, sn: str) -> list[dict]:
    """Return pending tasks and mark them dispatched.

    This is the single delivery path for ESP32 tasks. It includes system tasks
    and quick-diagnosis tasks because both are keyed by SN.
    """
    tasks = await list_pending_sensor_tasks(session, sn)
    if not tasks:
        return []
        
    now = datetime.utcnow()
    payloads = []
    
    for task in tasks:
        payload = await sensor_task_to_device_payload(session, task)
        if payload is not None:
            task.status = SENSOR_TASK_STATUS_DISPATCHED
            task.dispatched_at = now
            payloads.append(payload)
            
    if payloads:
        await session.commit()
        
    return payloads


async def record_sensor_task_report(
    *,
    session: AsyncSession,
    task_id: UUID | str,
    sn: str,
    sequence: int | None,
    report_id: str,
    ts_ms: int,
) -> SensorTask | None:
    """Record one task-generated upload and complete the task when val is met.

    The database keeps one row per task sequence. Duplicate uploads for the
    same task_id + sequence are ignored and do not increase completion count.
    """
    task_uuid = _parse_task_uuid(task_id)
    if task_uuid is None or sequence is None:
        return None
    if sequence < 1:
        return None

    task = await get_sensor_task_by_id(session, task_uuid)
    if task is None:
        return None
    if task.sn != sn or task.action <= 10:
        return None
    expected_count = int(task.val or 0)
    if expected_count < 1 or sequence > expected_count:
        return None
    if task.status == SENSOR_TASK_STATUS_PENDING:
        task.status = SENSOR_TASK_STATUS_DISPATCHED
        task.dispatched_at = task.dispatched_at or datetime.utcnow()

    existing = await _get_sensor_task_report(session, task_uuid, sequence)
    if existing is None:
        report_uuid = await _resolve_report_uuid(session, report_id)
        report = SensorTaskReport(
            task_id=task_uuid,
            sn=sn,
            sequence=sequence,
            report_id=report_id,
            report_uuid=report_uuid,
            ts_ms=ts_ms,
            created_at=datetime.utcnow(),
        )
        session.add(report)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            task = await get_sensor_task_by_id(session, task_uuid)
            if task is None:
                return None

    received_count = await count_sensor_task_reports(session, task_uuid, max_sequence=expected_count)
    if expected_count > 0 and received_count >= expected_count:
        task = await complete_sensor_task_by_id(session, task_uuid, commit=False)
    await session.commit()
    if task is not None:
        await session.refresh(task)
    return task


async def get_sensor_task_by_id(session: AsyncSession, task_id: UUID | str) -> SensorTask | None:
    """Return one SensorTask by id."""
    task_uuid = task_id if isinstance(task_id, UUID) else _parse_task_uuid(task_id)
    if task_uuid is None:
        return None
    stmt = select(SensorTask).where(SensorTask.id == task_uuid)
    return (await session.execute(stmt)).scalar_one_or_none()


async def count_sensor_task_reports(
    session: AsyncSession,
    task_id: UUID | str,
    *,
    max_sequence: int | None = None,
) -> int:
    """Count distinct report sequences received for one task."""
    task_uuid = task_id if isinstance(task_id, UUID) else _parse_task_uuid(task_id)
    if task_uuid is None:
        return 0
    stmt = select(func.count()).select_from(SensorTaskReport).where(SensorTaskReport.task_id == task_uuid)
    if max_sequence is not None:
        stmt = stmt.where(
            SensorTaskReport.sequence >= 1,
            SensorTaskReport.sequence <= max_sequence,
        )
    return int((await session.execute(stmt)).scalar_one() or 0)


async def complete_sensor_task_by_id(
    session: AsyncSession,
    task_id: UUID | str,
    *,
    commit: bool = True,
) -> SensorTask | None:
    """Mark a task complete."""
    task_uuid = _parse_task_uuid(task_id)
    if task_uuid is None:
        return None

    task = await get_sensor_task_by_id(session, task_uuid)
    if task is None:
        return None
    if task.status != SENSOR_TASK_STATUS_DONE:
        _mark_sensor_task_done(task)
        if commit:
            await session.commit()
            await session.refresh(task)
    return task


def _mark_sensor_task_done(task: SensorTask) -> None:
    task.status = SENSOR_TASK_STATUS_DONE
    task.complete_time = datetime.utcnow()
    task.dedupe_key = None


def _automatic_task_dedupe_key(
    *,
    sn: str,
    spec: SensorTaskSpec,
) -> str | None:
    if spec.kind == "resampling":
        purpose = TASK_PURPOSE_RESAMPLING
    elif spec.kind == "fft_collection":
        purpose = "FFT"
    else:
        return None
    return hashlib.sha256(f"{sn}:{purpose}".encode("utf-8")).hexdigest()


async def _get_sensor_task_report(
    session: AsyncSession,
    task_id: UUID,
    sequence: int,
) -> SensorTaskReport | None:
    stmt = select(SensorTaskReport).where(
        SensorTaskReport.task_id == task_id,
        SensorTaskReport.sequence == sequence,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _parse_task_uuid(task_id: UUID | str) -> UUID | None:
    try:
        return task_id if isinstance(task_id, UUID) else UUID(str(task_id))
    except (TypeError, ValueError):
        return None


def _parse_report_uuid(report_id: str | None) -> UUID | None:
    if not report_id:
        return None
    try:
        return UUID(str(report_id))
    except (TypeError, ValueError):
        return None


async def _resolve_report_uuid(session: AsyncSession, report_id: str) -> UUID | None:
    report_uuid = _parse_report_uuid(report_id)
    if report_uuid is None:
        return None
    stmt = select(DiagnosisRecord.id).where(DiagnosisRecord.id == report_uuid)
    return (await session.execute(stmt)).scalar_one_or_none()


async def find_equivalent_pending_collection_task(
    *,
    session: AsyncSession,
    sn: str,
    spec: SensorTaskSpec,
) -> SensorTask | None:
    """Find a pending task that already collects the requested data.

    For default-parameter dense collection, different focus codes collect the
    same full payload when interval and repeat count match. Reusing one pending
    task prevents temperature and RMS triggers from creating duplicate work.
    """
    if spec.kind == "default_dense_collection":
        interval = spec.action % 10
        stmt = (
            select(SensorTask)
            .where(
                SensorTask.sn == sn,
                SensorTask.status.in_(SENSOR_TASK_OPEN_STATUSES),
                SensorTask.val == spec.val,
                SensorTask.action > 10,
                SensorTask.action < FFT_COLLECTION_ACTION,
            )
            .order_by(SensorTask.create_time.desc())
        )
        tasks = (await session.execute(stmt)).scalars().all()
        for task in tasks:
            if task.action % 10 == interval:
                return task
        return None

    stmt = (
        select(SensorTask)
        .where(
            SensorTask.sn == sn,
            SensorTask.action == spec.action,
            SensorTask.val == spec.val,
            SensorTask.status.in_(SENSOR_TASK_OPEN_STATUSES),
        )
        .order_by(SensorTask.create_time.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _task_remark(*, spec: SensorTaskSpec, reason: str) -> str:
    return (
        f"任务内容: {spec.description}; "
        f"发起原因: {reason}; "
        f"编码: action={spec.action}, val={spec.val}; "
        "编码规则: 11..98 表示默认参数密集采集, action=T I, "
        "T=重点类型(1综合/2温度/3RMS/4冲击频谱), I=间隔分钟, "
        "val=重复次数; action=99 表示设备自主参数的 FFT 采集"
    )


def _require_repeat_count(repeat_count: int) -> None:
    _require_int_range("repeat_count", repeat_count, MIN_REPEAT_COUNT, 32767)


def _require_default_dense_focus(focus_type: int) -> None:
    if focus_type not in DEFAULT_DENSE_FOCUS_LABELS:
        raise ValueError("focus_type must be one of 1, 2, 3, 4")


def _require_int_range(name: str, value: int, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")


logger = logging.getLogger(__name__)

async def process_fft_metadata_background(task_id: UUID | str) -> bool:
    """Read device-selected FFT metadata and run diagnosis for action=99."""
    task_uuid = _parse_task_uuid(task_id)
    if not task_uuid:
        return False

    try:
        async with db_manager.SessionLocal() as session:
            task = await get_sensor_task_by_id(session, task_uuid)
            if not task:
                logger.error(f"FFT metadata process failed: SensorTask {task_uuid} not found")
                return False

            if task.action != FFT_COLLECTION_ACTION:
                logger.warning(
                    "FFT metadata process skipped: Task %s action %s is not FFT action 99",
                    task_uuid,
                    task.action,
                )
                return False

            import sys
            from pathlib import Path

            server_path = Path(__file__).parent.parent.parent.parent.parent.parent
            if str(server_path) not in sys.path:
                sys.path.append(str(server_path))

            from diagnosis.app.preparation.fft_parser import FftParser
            from diagnosis.app.handler.fft_analyzer import FftAnalyzer

            fft_data = FftParser.parse_from_minio(str(task_uuid))
            if fft_data is None:
                return False

            stmt_exist = select(DeviceFftRecord).where(DeviceFftRecord.task_id == task_uuid)
            record = (await session.execute(stmt_exist)).scalar_one_or_none()

            stmt = (
                select(SensorMonitoring)
                .join(Sensor, Sensor.id == SensorMonitoring.sensor_id)
                .where(Sensor.sn == task.sn)
            )
            monitoring = (await session.execute(stmt)).scalar_one_or_none()

            tenant_id = None
            sensor_id = None
            if monitoring:
                sensor_id = monitoring.sensor_id
                stmt_batch = (
                    select(SensorBatch.tenant_id)
                    .join(Sensor, Sensor.sensor_batch_id == SensorBatch.id)
                    .where(Sensor.sn == task.sn)
                )
                tenant_id = (await session.execute(stmt_batch)).scalar_one_or_none()

            if record is None:
                record = DeviceFftRecord(
                    task_id=task_uuid,
                    sn=task.sn,
                    sensor_id=sensor_id,
                    device_inst_id=monitoring.device_inst_id if monitoring else None,
                    tenant_id=tenant_id,
                    ts_ms=fft_data.timestamp_s * 1000,
                    fs_hz=round(fft_data.fs),
                    points=fft_data.points,
                    range_g=fft_data.range_g,
                )
                session.add(record)
            else:
                logger.info("FFT metadata already exists for task %s", task_uuid)
            await session.commit()
            logger.info(f"Successfully processed FFT metadata for task {task_uuid}")

            try:
                completed = await FftAnalyzer.analyze_and_save(
                    str(task_uuid),
                    fft_data,
                )
                if not completed:
                    return False
                _mark_sensor_task_done(task)
                await session.commit()
            except Exception as inner_e:
                logger.error(
                    f"Failed to execute FFT diagnostic engine for task {task_uuid}: {inner_e}",
                    exc_info=True,
                )
                return False

            return True

    except Exception as e:
        logger.error(f"Error processing FFT metadata for task {task_uuid}: {e}", exc_info=True)
        return False

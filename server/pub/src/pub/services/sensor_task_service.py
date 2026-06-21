"""
Sensor task generation helpers.

This module owns task action rules and completion paths.

Encoding rules:
- action=0: firmware upgrade, completed by the device callback API.
- action=1: config update, completed by the device callback API.
- action=3: device status report, completed with the status upload.
- action 11..99: default-parameter dense collection, encoded as T I.
  T = focus type, I = interval minutes, val = repeat count.
  Focus types: 1=general, 2=temperature, 3=RMS, 4=impact/spectrum.
  Example: action=15, val=3 -> collect full data every 5 minutes, repeat 3
  times.
  Example: action=25, val=3 -> collect full data every 5 minutes, repeat 3
  times with temperature as the server-side review focus.
- action 1000..9999: IIS3DWB parameterized dense collection, encoded as M RR I.
  M = FFT points multiplier of 4096.
  RR = range_g, one of 02, 04, 08, 16.
  I = interval minutes, 1..9.
  val = repeat count.
  Example: action=2086, val=3 -> 2*4096 FFT points, 8g range, every 6
  minutes, repeat 3 times.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pub.models.sensor import Sensor, SensorStatus, SensorTask, SensorTaskReport

SENSOR_TASK_STATUS_PENDING = 0
SENSOR_TASK_STATUS_DONE = 1
SENSOR_TASK_STATUS_DISPATCHED = 2
SENSOR_TASK_STATUS_FAILED = 3
SENSOR_TASK_OPEN_STATUSES = (SENSOR_TASK_STATUS_PENDING, SENSOR_TASK_STATUS_DISPATCHED)
SYSTEM_ACTION_FIRMWARE_UPGRADE = 0
SYSTEM_ACTION_CONFIG_UPDATE = 1
SYSTEM_ACTION_STATUS_REPORT = 2
SYSTEM_ACTIONS_COMPLETED_BY_CALLBACK = (
    SYSTEM_ACTION_FIRMWARE_UPGRADE,
    SYSTEM_ACTION_CONFIG_UPDATE,
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

PARAMETERIZED_MIN_ACTION = 1000
FFT_POINTS_BASE = 4096
ALLOWED_IIS3DWB_RANGE_G = {2, 4, 8, 16}
PARAMETERIZED_MIN_INTERVAL_MIN = 1
PARAMETERIZED_MAX_INTERVAL_MIN = 9
MIN_REPEAT_COUNT = 1

TaskKind = Literal["default_dense_collection", "iis3dwb_parameterized_collection"]


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


def build_iis3dwb_parameterized_collection_spec(
    *,
    fft_points_multiplier: int,
    range_g: int,
    interval_minutes: int,
    repeat_count: int,
) -> SensorTaskSpec:
    """Build action/val for IIS3DWB parameterized dense collection."""
    _require_int_range("fft_points_multiplier", fft_points_multiplier, 1, 9)
    if range_g not in ALLOWED_IIS3DWB_RANGE_G:
        raise ValueError("range_g must be one of 2, 4, 8, 16")
    _require_int_range(
        "interval_minutes",
        interval_minutes,
        PARAMETERIZED_MIN_INTERVAL_MIN,
        PARAMETERIZED_MAX_INTERVAL_MIN,
    )
    _require_repeat_count(repeat_count)

    action = fft_points_multiplier * 1000 + range_g * 10 + interval_minutes
    return SensorTaskSpec(
        action=action,
        val=repeat_count,
        kind="iis3dwb_parameterized_collection",
        description=(
            f"IIS3DWB 参数化密集采集：FFT Points={fft_points_multiplier}*"
            f"{FFT_POINTS_BASE}={fft_points_multiplier * FFT_POINTS_BASE}，"
            f"量程={range_g}g，每 {interval_minutes} 分钟采集一次完整数据，"
            f"重复 {repeat_count} 次"
        ),
    )


def describe_collection_action(action: int, val: int) -> str:
    """Return a human-readable description for a collection task action."""
    if 10 < action < 100:
        focus_type = action // 10
        interval = action % 10
        focus_label = DEFAULT_DENSE_FOCUS_LABELS.get(focus_type, f"未知重点({focus_type})")
        return (
            f"默认参数密集采集：重点={focus_label}，每 {interval} "
            f"分钟采集一次完整数据，重复 {val} 次"
        )

    if action >= PARAMETERIZED_MIN_ACTION:
        fft_points_multiplier = action // 1000
        range_g = (action // 10) % 100
        interval_minutes = action % 10
        return (
            f"IIS3DWB 参数化密集采集：FFT Points={fft_points_multiplier}*"
            f"{FFT_POINTS_BASE}={fft_points_multiplier * FFT_POINTS_BASE}，"
            f"量程={range_g}g，每 {interval_minutes} 分钟采集一次完整数据，"
            f"重复 {val} 次"
        )

    return f"系统任务：action={action}, val={val}"


async def create_collection_task(
    *,
    session: AsyncSession,
    sn: str,
    spec: SensorTaskSpec,
    reason: str,
    name: str | None = None,
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

    task = SensorTask(
        name=name or spec.kind,
        sn=sn,
        action=spec.action,
        val=spec.val,
        remark=_task_remark(spec=spec, reason=reason),
        status=SENSOR_TASK_STATUS_PENDING,
        create_time=datetime.utcnow(),
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
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
    sn: str,
    success: bool = True,
) -> SensorTask | None:
    """Complete an action 0/1 task after the device reports execution result."""
    task = await get_sensor_task_by_id(session, task_id)
    if (
        task is None
        or task.sn != sn
        or task.action not in SYSTEM_ACTIONS_COMPLETED_BY_CALLBACK
    ):
        return None
    target_status = SENSOR_TASK_STATUS_DONE if success else SENSOR_TASK_STATUS_FAILED
    if task.status != target_status:
        if target_status == SENSOR_TASK_STATUS_DONE:
            _mark_sensor_task_done(task)
        else:
            task.status = target_status
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
    battery: float | None = None,
    active: bool = True,
    task_id: UUID | str | None = None,
) -> SensorStatus:
    """Persist device status and atomically complete its action=3 task."""
    task = None
    if task_id is not None:
        task = await get_sensor_task_by_id(session, task_id)
        if task is None or task.sn != sn or task.action != SYSTEM_ACTION_STATUS_REPORT:
            logger.warning(f"Status report included invalid or non-status task_id {task_id} for sn {sn}, ignoring task completion.")
            task = None

    status = SensorStatus(
        sn=sn,
        ts=datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).replace(tzinfo=None),
        temperature=temperature,
        rssi=rssi,
        battery=battery,
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


async def create_iis3dwb_parameterized_collection_task(
    *,
    session: AsyncSession,
    sn: str,
    fft_points_multiplier: int,
    range_g: int,
    interval_minutes: int,
    repeat_count: int,
    reason: str,
) -> SensorTask:
    """Create an IIS3DWB parameterized dense collection task."""
    spec = build_iis3dwb_parameterized_collection_spec(
        fft_points_multiplier=fft_points_multiplier,
        range_g=range_g,
        interval_minutes=interval_minutes,
        repeat_count=repeat_count,
    )
    return await create_collection_task(
        session=session,
        sn=sn,
        spec=spec,
        reason=reason,
        name="iis3dwb_parameterized_collection",
    )


import json

def sensor_task_to_device_payload(task: SensorTask) -> dict:
    """Serialize a SensorTask in the compact shape expected by ESP32."""
    payload = {
        "id": str(task.id),
        "action": task.action,
        "val": task.val,
    }
    if task.action == SYSTEM_ACTION_FIRMWARE_UPGRADE and task.remark:
        try:
            remark_data = json.loads(task.remark)
            if "url" in remark_data:
                payload["val"] = remark_data["url"]
        except json.JSONDecodeError:
            # fallback if it's not a JSON string, just to be safe
            pass
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
    for task in tasks:
        task.status = SENSOR_TASK_STATUS_DISPATCHED
        task.dispatched_at = now
    await session.commit()
    return [sensor_task_to_device_payload(task) for task in tasks]


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
        report = SensorTaskReport(
            task_id=task_uuid,
            sn=sn,
            sequence=sequence,
            report_id=report_id,
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
                SensorTask.action < 100,
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
        "编码规则: 11..99 表示默认参数密集采集, action=T I, "
        "T=重点类型(1综合/2温度/3RMS/4冲击频谱), I=间隔分钟, "
        "val=重复次数; 1000..9999 表示 IIS3DWB 参数化密集采集, "
        "action=M RR I, M=4096 点倍数, RR=量程(02/04/08/16), "
        "I=间隔分钟, val=重复次数"
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


import logging
logger = logging.getLogger(__name__)

async def process_fft_metadata_background(task_id: UUID | str) -> None:
    """Parse FFT metadata from task action and store in DeviceFftRecord."""
    from pub.database import db_manager
    from pub.models.sensor import DeviceFftRecord, SensorMonitoring, SensorBatch

    task_uuid = _parse_task_uuid(task_id)
    if not task_uuid:
        return

    try:
        async with db_manager.SessionLocal() as session:
            task = await get_sensor_task_by_id(session, task_uuid)
            if not task:
                logger.error(f"FFT metadata process failed: SensorTask {task_uuid} not found")
                return

            # Ensure this is a parameterized FFT collection action
            if task.action < PARAMETERIZED_MIN_ACTION:
                logger.warning(f"FFT metadata process skipped: Task {task_uuid} action {task.action} is not parameterized FFT")
                return

            # Avoid duplicates
            stmt_exist = select(DeviceFftRecord).where(DeviceFftRecord.task_id == task_uuid)
            if (await session.execute(stmt_exist)).scalar_one_or_none():
                logger.info(f"FFT metadata already exists for task {task_uuid}")
                return

            # Parse specs from action
            fft_points_multiplier = task.action // 1000
            range_g = (task.action // 10) % 100
            points = fft_points_multiplier * FFT_POINTS_BASE

            # Get relationships
            stmt = select(SensorMonitoring).join(Sensor, Sensor.id == SensorMonitoring.sensor_id).where(Sensor.sn == task.sn)
            monitoring = (await session.execute(stmt)).scalar_one_or_none()
            
            # Note: We need tenant_id. We can get it from DeviceInst or SensorBatch. 
            # For now, we will leave tenant_id null if it's not directly accessible, or query it if needed.
            # SensorBatch is linked from Sensor.
            tenant_id = None
            sensor_id = None
            if monitoring:
                sensor_id = monitoring.sensor_id
                # Let's get tenant_id from SensorBatch
                stmt_batch = select(SensorBatch.tenant_id).join(Sensor, Sensor.sensor_batch_id == SensorBatch.id).where(Sensor.sn == task.sn)
                tenant_id = (await session.execute(stmt_batch)).scalar_one_or_none()

            record = DeviceFftRecord(
                task_id=task_uuid,
                sn=task.sn,
                sensor_id=sensor_id,
                device_inst_id=monitoring.device_inst_id if monitoring else None,
                tenant_id=tenant_id,
                ts_ms=int(datetime.utcnow().timestamp() * 1000),  # fallback timestamp
                fs_hz=26667,  # Default for IIS3DWB
                points=points,
                range_g=range_g
            )
            session.add(record)
            await session.commit()
            logger.info(f"Successfully processed FFT metadata for task {task_uuid}")
    except Exception as e:
        logger.error(f"Error processing FFT metadata for task {task_uuid}: {e}", exc_info=True)

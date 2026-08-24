import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from app.clients.mqtt import publish_notification_event
from pub.models.diagnosis import DiagnosisRecordStatus
from pub.models.report import DiagnosisTriggerPayload
from pub.services.diagnosis.diagnosis_record_service import DiagnosisRecordService

logger = logging.getLogger(__name__)

_device_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_BURST_STATE_TTL_SECONDS = 24 * 3600
_DIAGNOSIS_DONE_TTL_SECONDS = 30 * 24 * 3600


def _empty_burst_state() -> dict[str, Any]:
    return {
        "candidate": None,
        "expected_delayed": None,
        "observations": {},
    }


def _advance_burst_state(
    state: dict[str, Any] | None,
    report: DiagnosisTriggerPayload,
) -> tuple[dict[str, Any] | None, DiagnosisTriggerPayload | None]:
    """Advance one device's upload burst without depending on message arrival order.

    A delay=0 report is always the diagnosis target.  When total>0, all delayed
    reports with remaining totals N-1..0 must be observed before that target is
    diagnosed.  Report IDs make repeated stream deliveries idempotent.
    """
    delay = int(report.delay or 0)
    total = int(report.total)

    if delay == 0:
        if total == 0:
            return None, report

        previous = state or _empty_burst_state()
        # Preserve only observations that arrived before their candidate because
        # workers completed out of order. A new candidate replaces an older,
        # unfinished upload cycle and therefore clears the old observations.
        previous_candidate = previous.get("candidate")
        same_candidate = (
            previous_candidate is not None
            and previous_candidate.get("report_id") == report.report_id
        )
        observations = (
            previous.get("observations", {})
            if previous_candidate is None or same_candidate
            else {}
        )
        state = {
            "candidate": report.model_dump(mode="json"),
            "expected_delayed": total,
            "observations": observations,
        }
    else:
        state = state or _empty_burst_state()
        observations = state.setdefault("observations", {})
        observations[report.report_id] = {
            "total": total,
            "ts_ms": report.ts_ms,
        }

    candidate_data = state.get("candidate")
    expected = state.get("expected_delayed")
    if not candidate_data or not isinstance(expected, int) or expected <= 0:
        return state, None

    candidate = DiagnosisTriggerPayload.model_validate(candidate_data)
    observed_totals = {
        int(item["total"])
        for item in state.get("observations", {}).values()
        if int(item.get("ts_ms", candidate.ts_ms)) < candidate.ts_ms
    }
    required_totals = set(range(expected))
    if required_totals.issubset(observed_totals):
        return None, candidate

    return state, None

def severity_to_level(severity: str) -> int:
    mapping = {"ok": 0, "normal": 0, "info": 0, "attention": 1, "abnormal": 2, "warning": 3, "critical": 4}
    return mapping.get(severity.lower(), 0)


def _notification_schema_fields(
    schema_version: int,
    overall_level: int,
    fault_events: list[dict[str, Any]],
) -> dict[str, Any]:
    if schema_version == 1:
        return {"overall_level": overall_level}
    if schema_version == 2:
        return {"schema_version": 2, "faults": fault_events}
    raise ValueError("notification_event_schema_version must be 1 or 2")


async def _committed_fault_event(
    session: Any,
    source_record: Any,
    *,
    schema_version: int,
) -> dict[str, Any] | None:
    """Build an MQTT fault event only from committed diagnosis rows."""
    from sqlalchemy import select

    from pub.models.diagnosis import Diagnosis, DiagnosisItem

    diagnosis = (
        await session.execute(
            select(Diagnosis)
            .where(Diagnosis.report_uuid == source_record.id)
            .order_by(Diagnosis.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if diagnosis is None or int(diagnosis.overall_level or 0) <= 0:
        return None

    items = list(
        (
            await session.execute(
                select(DiagnosisItem).where(
                    DiagnosisItem.diagnosis_id == diagnosis.id,
                    DiagnosisItem.level > 0,
                )
            )
        ).scalars().all()
    )
    fault_events = [
        {
            "diagnosis_item_id": str(item.id),
            "fault_type": str(item.fault_type),
            "fault_level": int(item.level),
        }
        for item in items
    ]
    if schema_version == 2 and not fault_events:
        return None

    diagnosed_at = diagnosis.diagnosed_at
    if diagnosed_at.tzinfo is None:
        diagnosed_at = diagnosed_at.replace(tzinfo=timezone.utc)
    event = {
        "event_id": str(diagnosis.id),
        "diagnosis_id": str(diagnosis.id),
        "report_id": str(source_record.id),
        "device_id": str(diagnosis.device_id),
        "sensor_sn": source_record.sensor_sn,
        "device_category_id": (
            str(source_record.device_category_id)
            if source_record.device_category_id
            else None
        ),
        "process_device_id": (
            str(source_record.process_device_id)
            if source_record.process_device_id
            else None
        ),
        "diagnosed_at": diagnosed_at.isoformat(),
    }
    event.update(
        _notification_schema_fields(
            schema_version,
            int(diagnosis.overall_level),
            fault_events,
        )
    )
    return event


async def _publish_committed_fault_event(event: dict[str, Any] | None) -> None:
    if event is None:
        return
    if not await publish_notification_event(event):
        raise RuntimeError(
            "Failed to publish committed diagnosis fault event: "
            f"event_id={event.get('event_id')}"
        )


async def dispatch_diagnosis_trigger(report: DiagnosisTriggerPayload) -> int:
    logger.info("TRIGGER DIAGNOSIS: Executing diagnosis for device_id=%s", report.device_id)
    try:
        import uuid
        import asyncio
        from app.config import settings
        from app.services.context import DeviceContextService
        from app.handler.bearing import BearingDiagnosis
        from app.handler.temperature import TemperatureDiagnosis
        from app.handler.vibration import VibrationDiagnosis
        from pub.manager.database import db_manager, redis_manager
        from pub.models.diagnosis import (
            Diagnosis,
            DiagnosisCase,
            DiagnosisCaseAttempt,
            DiagnosisCaseAttemptPhase,
            DiagnosisCaseAttemptResultStatus,
            DiagnosisConfirmationStatus,
            DiagnosisFaultType,
            DiagnosisItem,
            DiagnosisRecord,
        )
        from pub.models.sensor import SensorTask, SensorTaskReport
        from pub.services.sensor.sensor_task_service import (
            create_resampling_task,
            ensure_resampling_followup_fft_task,
            find_open_resampling_task,
        )
        from sqlalchemy import or_, select
        from pub.utils.redis_keys import (
            REDIS_KEY_DASHBOARD_HEALTH_DIRTY,
            REDIS_KEY_DIA_AMBIENT_TEMP,
            REDIS_KEY_DIA_HEALTH_STATUS,
        )
        
        device_uuid = uuid.UUID(report.device_id)
        location_uuid = uuid.UUID(report.location_id)
        report_uuid = uuid.UUID(report.report_id)

        async with db_manager.SessionLocal() as session:
            source_record = await session.get(
                DiagnosisRecord,
                report_uuid,
            )
            if source_record is None:
                raise RuntimeError(
                    f"DiagnosisRecord not found for report_id={report.report_id}"
                )
            already_diagnosed = (
                source_record.diagnosis_status
                == int(DiagnosisRecordStatus.DIAGNOSED)
            )
            if already_diagnosed:
                committed_event = await _committed_fault_event(
                    session,
                    source_record,
                    schema_version=settings.notification_event_schema_version,
                )
                committed_level = int(source_record.overall_level or 0)
        if already_diagnosed:
            if committed_level > 0 and committed_event is None:
                raise RuntimeError(
                    "Committed fault diagnosis has no publishable event: "
                    f"report_id={report.report_id}"
                )
            await _publish_committed_fault_event(committed_event)
            return committed_level
        
        context = await DeviceContextService.get_by_device_id_managed(report.device_id)
        if not context:
            raise RuntimeError(
                f"No diagnosis context found for device_id={report.device_id}"
            )
            
        # Inject dynamic context from payload
        ambient_temperature = None
        if report.region_id:
            client = redis_manager.get_client()
            if client:
                try:
                    key = REDIS_KEY_DIA_AMBIENT_TEMP.format(region_id=report.region_id)
                    raw_temp = await asyncio.to_thread(client.get, key)
                    if raw_temp:
                        ambient_temperature = float(raw_temp)
                except Exception as e:
                    logger.warning("Failed to fetch ambient temperature from Redis: %s", e)
        context["ambient_temperature"] = ambient_temperature
        
        # Inject Peer Group
        peer_group = await DeviceContextService.get_peer_group_managed(report.process_device_id, report.device_category_id)
        context["peer_group"] = {"enabled": True, "members": peer_group}
            
        # Temperature Diagnosis
        temp_result = await TemperatureDiagnosis.analyze(
            report.device_id,
            report.location_id,
            report.temperature_c or 0.0,
            context,
            current_ts_ms=report.ts_ms,
        )
        temp_level = severity_to_level(temp_result.get("severity", "info"))
        
        # Vibration Diagnosis (Use max_rms_vel provided by persistence payload)
        max_rms_vel = report.max_rms_vel
        vib_result = await VibrationDiagnosis.analyze(
            report.device_id,
            report.location_id,
            max_rms_vel,
            context,
            current_ts_ms=report.ts_ms,
        )
        vib_level = severity_to_level(vib_result.get("severity", "info"))

        bearing_results = BearingDiagnosis.analyze(
            report.bearing_features,
            context,
            location_id=report.location_id,
            fs_hz=report.fs_hz,
            points=report.points,
        )
        bearing_level = max(
            (int(result["level"]) for result in bearing_results),
            default=0,
        )

        overall_level = max(temp_level, vib_level, bearing_level)

        redis_client = redis_manager.get_client()
        async with db_manager.SessionLocal() as session:
            async with session.begin():
                resampling_flag = 0
                source_record = await session.get(DiagnosisRecord, report_uuid)
                if source_record is None:
                    raise RuntimeError(
                        f"DiagnosisRecord not found for report_id={report.report_id}"
                    )

                task: SensorTask | None = None
                task_report: SensorTaskReport | None = None
                resampling_case: DiagnosisCase | None = None
                resampling_sequence: int | None = None
                if report.task_id:
                    try:
                        task_uuid = uuid.UUID(report.task_id)
                    except (TypeError, ValueError):
                        task_uuid = None
                    if task_uuid is not None:
                        task = await session.get(SensorTask, task_uuid)
                    if task is not None:
                        is_resampling_task = (
                            task.task_purpose == "RESAMPLING"
                            or (
                                task.action == 53
                                and "resampling" in (task.remark or "").lower()
                            )
                        )
                        if is_resampling_task:
                            report_identity_filters = [
                                SensorTaskReport.report_uuid == report_uuid,
                                SensorTaskReport.report_id == report.report_id,
                            ]
                            if report.task_sequence is not None:
                                report_identity_filters.append(
                                    SensorTaskReport.sequence
                                    == int(report.task_sequence)
                                )
                            task_report_stmt = select(SensorTaskReport).where(
                                SensorTaskReport.task_id == task.id,
                                or_(*report_identity_filters),
                            )
                            task_report = (
                                await session.execute(task_report_stmt)
                            ).scalar_one_or_none()
                            if task_report is None:
                                raise RuntimeError(
                                    "SensorTaskReport not found for resampling "
                                    f"task_id={task.id} report_id={report.report_id}"
                                )
                            resampling_sequence = int(task_report.sequence)
                            resampling_flag = int(
                                resampling_sequence < int(task.val or 0)
                            )
                            vib_result["evidence"]["confirmation_status"] = (
                                f"resampling_pass_{resampling_sequence}"
                                if resampling_flag
                                else "confirmed"
                            )
                            if task.diagnosis_case_id:
                                resampling_case = await session.get(
                                    DiagnosisCase,
                                    task.diagnosis_case_id,
                                )
                            else:
                                open_case_stmt = (
                                    select(DiagnosisCase)
                                    .where(
                                        DiagnosisCase.sensor_sn == report.sensor_sn,
                                        DiagnosisCase.fault_type
                                        == DiagnosisFaultType.VIBRATION.value,
                                        DiagnosisCase.confirmation_status
                                        == DiagnosisConfirmationStatus.RESAMPLING.value,
                                    )
                                    .order_by(DiagnosisCase.created_at.desc())
                                    .limit(1)
                                )
                                resampling_case = (
                                    await session.execute(open_case_stmt)
                                ).scalar_one_or_none()
                                if resampling_case is not None:
                                    task.diagnosis_case_id = resampling_case.id
                                    resampling_case.resampling_task_id = task.id

                ds_val = "服务端任务"
                if not report.task_id:
                    ds_val = "常规检查"
                elif str(report.task_id) == "0":
                    ds_val = "异常唤醒"
                elif task is not None and resampling_sequence is not None:
                    ds_val = f"复采任务({resampling_sequence}/{task.val})"

                # Persist anomaly diagnosis rows. Normal resampling conclusions
                # are captured below as case attempts without inventing items.
                diag_record: Diagnosis | None = None
                item_temp: DiagnosisItem | None = None
                item_vib: DiagnosisItem | None = None
                if overall_level > 0:
                    diag_record = Diagnosis(
                        device_id=device_uuid,
                        location_id=location_uuid,
                        report_id=report.report_id,
                        report_uuid=report_uuid,
                        overall_level=overall_level,
                        resampling=resampling_flag,
                        ds=ds_val,
                    )
                    session.add(diag_record)
                    await session.flush()
                    
                    if temp_level > 0:
                        item_temp = DiagnosisItem(
                            diagnosis_id=diag_record.id,
                            metric_id=0,
                            fault_type=DiagnosisFaultType.TEMPERATURE.value,
                            level=temp_level,
                            resampling=resampling_flag,
                            description=temp_result.get("reason"),
                            evidence=temp_result.get("evidence", {}),
                        )
                        session.add(item_temp)
                    
                    if vib_level > 0:
                        item_vib = DiagnosisItem(
                            diagnosis_id=diag_record.id,
                            metric_id=1,
                            fault_type=DiagnosisFaultType.VIBRATION.value,
                            level=vib_level,
                            resampling=resampling_flag,
                            description=vib_result.get("reason"),
                            evidence=vib_result.get("evidence", {}),
                        )
                        session.add(item_vib)

                    for bearing_result in bearing_results:
                        item_bearing = DiagnosisItem(
                            diagnosis_id=diag_record.id,
                            metric_id=int(bearing_result["metric_id"]),
                            fault_type=f"bearing_{bearing_result['fault_code']}",
                            level=int(bearing_result["level"]),
                            resampling=0,
                            description=bearing_result["description"],
                            evidence=bearing_result["evidence"],
                        )
                        session.add(item_bearing)
                    await session.flush()

                diagnosed_at = datetime.now(timezone.utc)
                source_record.diagnosis_status = int(
                    DiagnosisRecordStatus.DIAGNOSED
                )
                source_record.overall_level = overall_level
                source_record.diagnosed_at = diagnosed_at.replace(tzinfo=None)

                # Temperature uses the same case/attempt read model but does not
                # require confirmation or FFT.
                if item_temp is not None and diag_record is not None:
                    temp_case = DiagnosisCase(
                        root_report_id=report_uuid,
                        device_id=device_uuid,
                        sensor_sn=report.sensor_sn,
                        fault_type=DiagnosisFaultType.TEMPERATURE.value,
                        confirmation_status=(
                            DiagnosisConfirmationStatus.CONFIRMED_ABNORMAL.value
                        ),
                        confirmed_at=diagnosed_at.replace(tzinfo=None),
                    )
                    session.add(temp_case)
                    await session.flush()
                    session.add(
                        DiagnosisCaseAttempt(
                            case_id=temp_case.id,
                            report_id=report_uuid,
                            diagnosis_id=diag_record.id,
                            diagnosis_item_id=item_temp.id,
                            phase=DiagnosisCaseAttemptPhase.INITIAL.value,
                            sequence=0,
                            result_status=(
                                DiagnosisCaseAttemptResultStatus.ABNORMAL.value
                            ),
                            fault_level=temp_level,
                            description=item_temp.description,
                            evidence=item_temp.evidence,
                            diagnosed_at=diagnosed_at.replace(tzinfo=None),
                        )
                    )

                if resampling_case is not None and task is not None:
                    is_final_attempt = (
                        resampling_sequence is not None
                        and resampling_sequence >= int(task.val or 0)
                    )
                    if is_final_attempt:
                        resampling_flag = 0
                        if vib_level >= 2:
                            resampling_case.confirmation_status = (
                                DiagnosisConfirmationStatus.CONFIRMED_ABNORMAL.value
                            )
                            resampling_case.confirmed_at = diagnosed_at.replace(
                                tzinfo=None
                            )
                            await ensure_resampling_followup_fft_task(
                                session=session,
                                resampling_task_id=task.id,
                                reason=(
                                    "深度诊断兜底：最终复采确认振动等级 "
                                    f"{vib_level}，需要 FFT"
                                ),
                                commit=False,
                            )
                        else:
                            resampling_case.confirmation_status = (
                                DiagnosisConfirmationStatus.RESOLVED_NORMAL.value
                            )
                    else:
                        resampling_case.confirmation_status = (
                            DiagnosisConfirmationStatus.RESAMPLING.value
                        )

                    session.add(
                        DiagnosisCaseAttempt(
                            case_id=resampling_case.id,
                            report_id=report_uuid,
                            diagnosis_id=diag_record.id if diag_record else None,
                            diagnosis_item_id=item_vib.id if item_vib else None,
                            phase=DiagnosisCaseAttemptPhase.RESAMPLE.value,
                            sequence=int(resampling_sequence or 0),
                            result_status=(
                                DiagnosisCaseAttemptResultStatus.ABNORMAL.value
                                if vib_level > 0
                                else DiagnosisCaseAttemptResultStatus.NORMAL.value
                            ),
                            fault_level=vib_level,
                            description=vib_result.get("reason"),
                            evidence=vib_result.get("evidence", {}),
                            diagnosed_at=diagnosed_at.replace(tzinfo=None),
                        )
                    )
                elif item_vib is not None and diag_record is not None:
                    requires_resampling = (
                        vib_level >= 2
                        and bool(vib_result.get("requires_resampling"))
                    )
                    vib_case = DiagnosisCase(
                        root_report_id=report_uuid,
                        device_id=device_uuid,
                        sensor_sn=report.sensor_sn,
                        fault_type=DiagnosisFaultType.VIBRATION.value,
                        confirmation_status=(
                            DiagnosisConfirmationStatus.RESAMPLING.value
                            if requires_resampling
                            else DiagnosisConfirmationStatus.CONFIRMED_ABNORMAL.value
                        ),
                        confirmed_at=(
                            None
                            if requires_resampling
                            else diagnosed_at.replace(tzinfo=None)
                        ),
                    )
                    session.add(vib_case)
                    await session.flush()
                    session.add(
                        DiagnosisCaseAttempt(
                            case_id=vib_case.id,
                            report_id=report_uuid,
                            diagnosis_id=diag_record.id,
                            diagnosis_item_id=item_vib.id,
                            phase=DiagnosisCaseAttemptPhase.INITIAL.value,
                            sequence=0,
                            result_status=(
                                DiagnosisCaseAttemptResultStatus.ABNORMAL.value
                            ),
                            fault_level=vib_level,
                            description=item_vib.description,
                            evidence=item_vib.evidence,
                            diagnosed_at=diagnosed_at.replace(tzinfo=None),
                        )
                    )
                    if requires_resampling:
                        resampling_flag = 1
                        diag_record.resampling = 1
                        vib_result["evidence"]["confirmation_status"] = (
                            "pending_confirmation"
                        )
                        resampling_task = await find_open_resampling_task(
                            session,
                            report.sensor_sn,
                        )
                        if resampling_task is None:
                            resampling_task = await create_resampling_task(
                                session=session,
                                sn=report.sensor_sn,
                                reason=(
                                    "深度诊断兜底：快速决策窗口后发现 "
                                    f"振动等级 {vib_level}，需要复采"
                                ),
                                commit=False,
                            )
                            logger.warning(
                                "Deep diagnosis created delayed fallback "
                                "resampling task: report_id=%s task_id=%s",
                                report.report_id,
                                resampling_task.id,
                            )
                        resampling_task.diagnosis_case_id = vib_case.id
                        resampling_task.source_report_id = report_uuid
                        resampling_task.source_diagnosis_id = diag_record.id
                        resampling_task.task_purpose = "RESAMPLING"
                        vib_case.resampling_task_id = resampling_task.id

        async with db_manager.SessionLocal() as session:
            committed_source = await session.get(DiagnosisRecord, report_uuid)
            if committed_source is None:
                raise RuntimeError(
                    f"DiagnosisRecord not found after commit: report_id={report.report_id}"
                )
            committed_event = await _committed_fault_event(
                session,
                committed_source,
                schema_version=settings.notification_event_schema_version,
            )
        if overall_level > 0 and committed_event is None:
            raise RuntimeError(
                "Committed fault diagnosis has no publishable event: "
                f"report_id={report.report_id}"
            )
        await _publish_committed_fault_event(committed_event)

        # 3. Update Health Status Cache
        if redis_client:
            try:
                await asyncio.to_thread(redis_client.hset, REDIS_KEY_DIA_HEALTH_STATUS, str(device_uuid), overall_level)
                if report.tenant_id:
                    tenant_key = str(uuid.UUID(report.tenant_id))
                    dirty_at_ms = int(time.time() * 1000)
                    await asyncio.to_thread(
                        redis_client.hset,
                        REDIS_KEY_DASHBOARD_HEALTH_DIRTY,
                        tenant_key,
                        dirty_at_ms,
                    )
            except Exception as e:
                logger.error("Failed to update health status cache: %s", e)
                
        logger.info("Successfully persisted diagnosis results to MySQL: overall_level=%s", overall_level)
        return overall_level
    except Exception as e:
        logger.error("Failed to execute diagnosis trigger: %s", str(e), exc_info=True)
        raise

async def process_incoming_report(report: DiagnosisTriggerPayload) -> None:
    """
    Process an incoming diagnostic report from the edge/hardware.
    """
    logger.debug(
        "Received report: id=%s, device_id=%s, sensor_sn=%s, ts_ms=%s, delay=%s, total=%s",
        report.report_id,
        report.device_id,
        report.sensor_sn,
        report.ts_ms,
        report.delay,
        report.total,
    )

    # 1. (Removed) InfluxDB writing is now handled by the 'persistence' application.

    # 2. Burst processing & Check if we should trigger diagnosis.
    from pub.manager.database import redis_manager
    from pub.utils.redis_keys import (
        REDIS_KEY_DIA_BURST_STATE,
        REDIS_KEY_DIA_DIAGNOSED_REPORT,
    )
    redis_client = redis_manager.get_client()
    burst_state_key = REDIS_KEY_DIA_BURST_STATE.format(device_id=report.device_id)

    async with _device_locks[report.device_id]:
        raw_state = await asyncio.to_thread(redis_client.get, burst_state_key)
        state = None
        if raw_state:
            try:
                state = json.loads(raw_state)
            except (TypeError, ValueError):
                logger.warning(
                    "Discarding invalid burst state for device_id=%s",
                    report.device_id,
                )

        if int(report.delay or 0) == 0:
            updated = await DiagnosisRecordService.mark_waiting_as_missed_managed(
                device_id=report.device_id,
                current_report_id=report.report_id,
            )
            if not updated:
                raise RuntimeError(
                    "Failed to close previous waiting diagnosis records: "
                    f"device_id={report.device_id}"
                )

        next_state, target_report = _advance_burst_state(state, report)

        if target_report is None:
            await asyncio.to_thread(
                redis_client.setex,
                burst_state_key,
                _BURST_STATE_TTL_SECONDS,
                json.dumps(next_state, separators=(",", ":")),
            )
            logger.debug(
                "Waiting for a complete delayed upload: device_id=%s delay=%s total=%s",
                report.device_id,
                report.delay,
                report.total,
            )
            return

        # Clear only after diagnosis succeeds. If diagnosis raises, the stream
        # message remains unacknowledged and the saved state can be retried.
        done_key = REDIS_KEY_DIA_DIAGNOSED_REPORT.format(
            report_id=target_report.report_id
        )
        already_diagnosed = await asyncio.to_thread(redis_client.exists, done_key)
        if not already_diagnosed:
            await dispatch_diagnosis_trigger(target_report)

        pipeline = redis_client.pipeline()
        pipeline.set(done_key, "1", ex=_DIAGNOSIS_DONE_TTL_SECONDS)
        pipeline.delete(burst_state_key)
        await asyncio.to_thread(pipeline.execute)

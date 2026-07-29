import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

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

async def dispatch_diagnosis_trigger(report: DiagnosisTriggerPayload) -> int:
    logger.info("TRIGGER DIAGNOSIS: Executing diagnosis for device_id=%s", report.device_id)
    try:
        import uuid
        import asyncio
        from app.services.context import DeviceContextService
        from app.handler.temperature import TemperatureDiagnosis
        from app.handler.vibration import VibrationDiagnosis
        from pub.manager.database import db_manager, redis_manager
        from pub.models.diagnosis import (
            Diagnosis,
            DiagnosisItem,
            DiagnosisRecord,
        )
        from pub.models.sensor import SensorTask
        from pub.utils.redis_keys import (
            REDIS_KEY_DASHBOARD_HEALTH_DIRTY,
            REDIS_KEY_DIA_AMBIENT_TEMP,
            REDIS_KEY_DIA_HEALTH_STATUS,
            REDIS_KEY_TASK_SEQ,
        )
        
        device_uuid = uuid.UUID(report.device_id)
        location_uuid = uuid.UUID(report.location_id)

        async with db_manager.SessionLocal() as session:
            source_record = await session.get(
                DiagnosisRecord,
                uuid.UUID(report.report_id),
            )
            if source_record is None:
                raise RuntimeError(
                    f"DiagnosisRecord not found for report_id={report.report_id}"
                )
            if (
                source_record.diagnosis_status
                == int(DiagnosisRecordStatus.DIAGNOSED)
            ):
                return int(source_record.overall_level or 0)
        
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
        
        overall_level = max(temp_level, vib_level)

        notification_event: dict[str, Any] | None = None
        async with db_manager.SessionLocal() as session:
            async with session.begin():
                resampling_flag = 0
                trigger_fft = False
                
                redis_client = redis_manager.get_client()
                
                # 1. Update Sequence Tracking & Evaluate Resampling Status
                if report.task_id:
                    seq_key = REDIS_KEY_TASK_SEQ.format(task_id=report.task_id)
                    seq_str = await asyncio.to_thread(redis_client.get, seq_key) if redis_client else None
                    if seq_str:
                        seq = int(seq_str) + 1
                        await asyncio.to_thread(redis_client.setex, seq_key, 86400, seq)
                        
                        if seq < 3:
                            resampling_flag = 1
                            vib_result["evidence"]["confirmation_status"] = f"resampling_pass_{seq}"
                        else:
                            resampling_flag = 0
                            vib_result["evidence"]["confirmation_status"] = "confirmed"
                            if vib_level >= 2:
                                trigger_fft = True
                else:
                    # Initial Trigger Check
                    if vib_level >= 2 and vib_result.get("requires_resampling"):
                        resampling_flag = 1
                        vib_result["evidence"]["confirmation_status"] = "pending_confirmation"
                        
                        new_task = SensorTask(
                            name="Vibration Re-sampling (Auto)",
                            sn=report.sensor_sn,
                            action=53,
                            val=3,
                            remark="Vibration anomaly triggered resampling",
                            status=0
                        )
                        session.add(new_task)
                        await session.flush()
                        
                        if redis_client:
                            seq_key = REDIS_KEY_TASK_SEQ.format(task_id=new_task.id)
                            await asyncio.to_thread(redis_client.setex, seq_key, 86400, 1)

                if trigger_fft:
                    fft_task = SensorTask(
                        name="FFT Data Collection (Auto)",
                        sn=report.sensor_sn,
                        action=908,  # Default 8G FFT for now
                        val=0,
                        remark="Confirmed anomaly triggered FFT",
                        status=0
                    )
                    session.add(fft_task)

                # 2. Persist Diagnosis (仅异常结果落库；正常结论只更新 Redis，不写 MySQL)
                if overall_level > 0:
                    diag_record = Diagnosis(
                        device_id=device_uuid,
                        location_id=location_uuid,
                        report_id=report.report_id,
                        overall_level=overall_level,
                        resampling=resampling_flag
                    )
                    session.add(diag_record)
                    await session.flush()
                    
                    # Temperature Item（只在异常时写入）
                    if temp_level > 0:
                        item_temp = DiagnosisItem(
                            diagnosis_id=diag_record.id,
                            metric_id=0, # Temperature
                            level=temp_level,
                            resampling=resampling_flag,
                            description=temp_result.get("reason"),
                            evidence=temp_result.get("evidence", {})
                        )
                        session.add(item_temp)
                    
                    # Vibration Item（只在异常时写入）
                    if vib_level > 0:
                        item_vib = DiagnosisItem(
                            diagnosis_id=diag_record.id,
                            metric_id=1, # Vibration
                            level=vib_level,
                            resampling=resampling_flag,
                            description=vib_result.get("reason"),
                            evidence=vib_result.get("evidence", {})
                        )
                        session.add(item_vib)

                source_record = await session.get(
                    DiagnosisRecord,
                    uuid.UUID(report.report_id),
                )
                if source_record is None:
                    raise RuntimeError(
                        f"DiagnosisRecord not found for report_id={report.report_id}"
                    )
                diagnosed_at = datetime.now(timezone.utc)
                source_record.diagnosis_status = int(
                    DiagnosisRecordStatus.DIAGNOSED
                )
                source_record.overall_level = overall_level
                source_record.diagnosed_at = diagnosed_at.replace(tzinfo=None)

                if overall_level > 0:
                    notification_event = {
                        "event_id": str(diag_record.id),
                        "diagnosis_id": str(diag_record.id),
                        "report_id": report.report_id,
                        "device_id": str(device_uuid),
                        "sensor_sn": report.sensor_sn,
                        "overall_level": overall_level,
                        "device_category_id": (
                            str(source_record.device_category_id)
                            if source_record.device_category_id
                            else report.device_category_id
                        ),
                        "process_device_id": (
                            str(source_record.process_device_id)
                            if source_record.process_device_id
                            else report.process_device_id
                        ),
                        "diagnosed_at": diagnosed_at.isoformat(),
                    }

        if notification_event is not None:
            try:
                from app.clients.mqtt import publish_notification_event

                await publish_notification_event(notification_event)
            except Exception:
                logger.error(
                    "Unexpected diagnosis notification publish failure: "
                    "diagnosis_id=%s",
                    notification_event["diagnosis_id"],
                    exc_info=True,
                )

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

import asyncio
import logging
from typing import Any

from pub.models.report import DiagnosisTriggerPayload

logger = logging.getLogger(__name__)

def severity_to_level(severity: str) -> int:
    mapping = {"ok": 0, "normal": 0, "info": 0, "attention": 1, "abnormal": 2, "warning": 3, "critical": 4}
    return mapping.get(severity.lower(), 0)

async def dispatch_diagnosis_trigger(report: DiagnosisTriggerPayload) -> None:
    logger.info("TRIGGER DIAGNOSIS: Executing diagnosis for device_id=%s", report.device_id)
    try:
        import uuid
        import asyncio
        from app.services.context import DeviceContextService
        from app.handler.temperature import TemperatureDiagnosis
        from app.handler.vibration import VibrationDiagnosis
        from pub.manager.database import db_manager, redis_manager
        from pub.models.diagnosis import Diagnosis, DiagnosisItem
        from pub.models.sensor import SensorTask
        from pub.utils.redis_keys import REDIS_KEY_DIA_AMBIENT_TEMP, REDIS_KEY_TASK_SEQ
        
        device_uuid = uuid.UUID(report.device_id)
        location_uuid = uuid.UUID(report.location_id)
        
        context = await DeviceContextService.get_by_device_id_managed(report.device_id)
        if not context:
            logger.warning("No context found for device_id=%s, skipping diagnosis.", report.device_id)
            return
            
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
        temp_result = await TemperatureDiagnosis.analyze(report.device_id, report.location_id, report.temperature_c or 0.0, context)
        temp_level = severity_to_level(temp_result.get("severity", "info"))
        
        # Vibration Diagnosis (Use max_rms_vel provided by persistence payload)
        max_rms_vel = report.max_rms_vel
        vib_result = await VibrationDiagnosis.analyze(report.device_id, report.location_id, max_rms_vel, context)
        vib_level = severity_to_level(vib_result.get("severity", "info"))
        
        overall_level = max(temp_level, vib_level)
        
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

                # 2. Persist Diagnosis (Insert new results)
                diag_record = Diagnosis(
                    device_id=device_uuid,
                    location_id=location_uuid,
                    report_id=report.report_id,
                    overall_level=overall_level,
                    resampling=resampling_flag
                )
                session.add(diag_record)
                await session.flush()
                
                # Temperature Item
                item_temp = DiagnosisItem(
                    diagnosis_id=diag_record.id,
                    metric_id=0, # Temperature
                    level=temp_level,
                    resampling=resampling_flag,
                    description=temp_result.get("reason"),
                    evidence=temp_result.get("evidence", {})
                )
                session.add(item_temp)
                
                # Vibration Item
                item_vib = DiagnosisItem(
                    diagnosis_id=diag_record.id,
                    metric_id=1, # Vibration
                    level=vib_level,
                    resampling=resampling_flag,
                    description=vib_result.get("reason"),
                    evidence=vib_result.get("evidence", {})
                )
                session.add(item_vib)
                
        logger.info("Successfully persisted diagnosis results to MySQL: overall_level=%s", overall_level)
    except Exception as e:
        logger.error("Failed to execute diagnosis trigger: %s", str(e), exc_info=True)

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
    redis_client = redis_manager.get_client()
    burst_head_key = f"dia:burst:head:{report.device_id}"
    
    target_report = report
    
    if report.total > 0:
        existing = await asyncio.to_thread(redis_client.get, burst_head_key)
        should_update = True
        if existing:
            try:
                existing_report = DiagnosisTriggerPayload.model_validate_json(existing)
                # Keep the report with the largest ts_ms (most recent sampling time)
                if report.ts_ms <= existing_report.ts_ms:
                    should_update = False
            except Exception:
                pass # Invalid cache, overwrite it
                
        if should_update:
            await asyncio.to_thread(redis_client.setex, burst_head_key, 3600, report.model_dump_json())
            
        logger.debug(
            "Data buffered. Waiting for %s more packets before triggering diagnosis for device_id=%s",
            report.total,
            report.device_id,
        )
    else:
        # report.total == 0
        existing = await asyncio.to_thread(redis_client.get, burst_head_key)
        if existing:
            try:
                existing_report = DiagnosisTriggerPayload.model_validate_json(existing)
                # Ensure the cached report is actually newer than this total=0 report
                if existing_report.ts_ms > report.ts_ms:
                    target_report = existing_report
                    logger.info(
                        "Using cached burst head (ts_ms=%s, total=%s) instead of current total=0 report (ts_ms=%s) for diagnosis.",
                        existing_report.ts_ms, existing_report.total, report.ts_ms
                    )
            except Exception as e:
                logger.warning("Failed to parse cached burst head: %s", e)
            
            # Clear the cache since the burst is complete
            await asyncio.to_thread(redis_client.delete, burst_head_key)
        
        logger.debug(
            "Batch complete (total=0) for device_id=%s. Triggering background diagnosis.",
            report.device_id,
        )
        await dispatch_diagnosis_trigger(target_report)

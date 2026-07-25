import logging
from typing import Any

from app.preparation.payload import DeviceDiagnosticReport

logger = logging.getLogger(__name__)

def severity_to_level(severity: str) -> int:
    mapping = {"ok": 0, "normal": 0, "info": 0, "attention": 1, "abnormal": 2, "warning": 3, "critical": 4}
    return mapping.get(severity.lower(), 0)

async def dispatch_diagnosis_trigger(report: DeviceDiagnosticReport) -> None:
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
        
        # Vibration Diagnosis (Extract max rms_vel_mm_s)
        max_rms_vel = 0.0
        if report.axis_features:
            max_rms_vel = max((axis.time.rms_vel_mm_s or 0.0) for axis in report.axis_features.values() if axis.time)
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

                # 2. Persist Diagnosis
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

async def process_incoming_report(report: DeviceDiagnosticReport) -> None:
    """
    Process an incoming diagnostic report from the edge/hardware.
    """
    logger.info(
        "Received report: id=%s, device_id=%s, sensor_sn=%s, ts_ms=%s, delay=%s, total=%s",
        report.report_id,
        report.device_id,
        report.sensor_sn,
        report.ts_ms,
        report.delay,
        report.total,
    )

    # 1. Store the raw/time-series data.
    try:
        from pub.manager.database import influxdb_manager
        from influxdb_client import Point
        from influxdb_client.client.write_api import SYNCHRONOUS
        import math

        client = influxdb_manager.get_client()
        write_api = client.write_api(write_options=SYNCHRONOUS)
        
        point = Point("vibration_feature") \
            .tag("sn", report.sensor_sn) \
            .tag("location_id", report.location_id) \
            .tag("device_id", report.device_id)
            
        if report.temperature_c is not None:
            point = point.field("temperature", float(report.temperature_c))
        
        rms_x = report.axis_features["X"].time.rms_acc_g if "X" in report.axis_features and report.axis_features["X"].time else 0.0
        rms_y = report.axis_features["Y"].time.rms_acc_g if "Y" in report.axis_features and report.axis_features["Y"].time else 0.0
        rms_z = report.axis_features["Z"].time.rms_acc_g if "Z" in report.axis_features and report.axis_features["Z"].time else 0.0
        
        rms_vel_x = report.axis_features["X"].time.rms_vel_mm_s if "X" in report.axis_features and report.axis_features["X"].time else 0.0
        rms_vel_y = report.axis_features["Y"].time.rms_vel_mm_s if "Y" in report.axis_features and report.axis_features["Y"].time else 0.0
        rms_vel_z = report.axis_features["Z"].time.rms_vel_mm_s if "Z" in report.axis_features and report.axis_features["Z"].time else 0.0
        
        if rms_x is not None: point = point.field("rms_x", float(rms_x))
        if rms_y is not None: point = point.field("rms_y", float(rms_y))
        if rms_z is not None: point = point.field("rms_z", float(rms_z))
        
        if rms_vel_x is not None: point = point.field("rms_vel_x", float(rms_vel_x))
        if rms_vel_y is not None: point = point.field("rms_vel_y", float(rms_vel_y))
        if rms_vel_z is not None: point = point.field("rms_vel_z", float(rms_vel_z))
        
        max_rms_vel = max(float(rms_vel_x or 0), float(rms_vel_y or 0), float(rms_vel_z or 0))
        point = point.field("max_rms_vel", max_rms_vel)
        
        if rms_x is not None and rms_y is not None and rms_z is not None:
            rms_m = math.sqrt(rms_x**2 + rms_y**2 + rms_z**2)
            point = point.field("rms_m", float(rms_m))
            
        point = point.time(report.ts_ms, write_precision="ms")
        
        logger.info("Persisting to InfluxDB: %s", point.to_line_protocol())
        write_api.write(bucket=influxdb_manager.bucket, org=influxdb_manager.org, record=point)
    except Exception as e:
        logger.error("Failed to insert raw waveform data into InfluxDB: %s", str(e), exc_info=True)

    # 2. Check if we should trigger diagnosis.
    if report.total == 0:
        logger.info(
            "Batch complete (total=0) for device_id=%s. Triggering background diagnosis.",
            report.device_id,
        )
        await dispatch_diagnosis_trigger(report)
    else:
        logger.debug(
            "Data buffered. Waiting for %s more packets before triggering diagnosis for device_id=%s",
            report.total,
            report.device_id,
        )

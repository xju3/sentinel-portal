import logging
from typing import Any

from app.preparation.payload import DeviceDiagnosticReport

logger = logging.getLogger(__name__)

def severity_to_level(severity: str) -> int:
    mapping = {"ok": 0, "normal": 0, "info": 0, "attention": 1, "abnormal": 2, "warning": 3, "critical": 4}
    return mapping.get(severity.lower(), 0)

async def dispatch_diagnosis_trigger(device_id: str, location_id: str, report_id: str, current_temp: float, trigger_ts: int) -> None:
    logger.info("TRIGGER DIAGNOSIS: Executing diagnosis for device_id=%s", device_id)
    try:
        import uuid
        from app.services.context import DeviceContextService
        from app.handler.temperature import TemperatureDiagnosis
        from pub.manager.database import db_manager
        from pub.models.diagnosis import Diagnosis, DiagnosisItem
        
        device_uuid = uuid.UUID(device_id)
        location_uuid = uuid.UUID(location_id)
        
        context = await DeviceContextService.get_by_device_id_managed(device_uuid)
        if not context:
            logger.warning("No context found for device_id=%s, skipping diagnosis.", device_id)
            return
            
        result = await TemperatureDiagnosis.analyze(device_id, location_id, current_temp, context)
        level = severity_to_level(result.get("severity", "info"))
        
        async with db_manager.SessionLocal() as session:
            async with session.begin():
                diag_record = Diagnosis(
                    device_id=device_uuid,
                    location_id=location_uuid,
                    report_id=report_id,
                    overall_level=level
                )
                session.add(diag_record)
                await session.flush()
                
                item = DiagnosisItem(
                    diagnosis_id=diag_record.id,
                    metric_id=0, # Temperature
                    level=level,
                    description=result.get("reason"),
                    evidence={"ratio": result.get("ratio"), "peer_median": result.get("peer_median"), "effective_rise": result.get("effective_rise")}
                )
                session.add(item)
        logger.info("Successfully persisted diagnosis results to MySQL: level=%s, reason=%s", level, result.get("reason"))
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
        
        if rms_x is not None: point = point.field("rms_x", float(rms_x))
        if rms_y is not None: point = point.field("rms_y", float(rms_y))
        if rms_z is not None: point = point.field("rms_z", float(rms_z))
        
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
        await dispatch_diagnosis_trigger(
            device_id=report.device_id,
            location_id=report.location_id,
            report_id=report.report_id,
            current_temp=report.temperature_c or 0.0,
            trigger_ts=report.ts_ms,
        )
    else:
        logger.debug(
            "Data buffered. Waiting for %s more packets before triggering diagnosis for device_id=%s",
            report.total,
            report.device_id,
        )

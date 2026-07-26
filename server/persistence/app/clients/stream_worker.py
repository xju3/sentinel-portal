import asyncio
import json
import uuid

from pub.manager.database import minio_manager, redis_manager, influxdb_manager
import logging
from pub.utils.redis_keys import (
    REDIS_STREAM_PERSISTENCE_INGEST,
    REDIS_STREAM_PERSISTENCE_GROUP,
    REDIS_STREAM_DIAGNOSIS_TRIGGER,
)
from pub.services.diagnosis.diagnosis_context_service import DiagnosisContextService
from pub.services.diagnosis.diagnosis_record_service import DiagnosisRecordService
from pub.models.report import DeviceDiagnosticReport

from app.config import settings

logger = logging.getLogger("persistence-stream")
_workers = []

async def _process_stream_message(bucket: str, path: str) -> bool:
    try:
        # 1. Fetch JSON from MinIO
        data_bytes = await minio_manager.get_object(bucket, path)
        if not data_bytes:
            logger.error(f"Failed to fetch {path} from MinIO")
            return False
            
        payload = json.loads(data_bytes.decode("utf-8"))
        report = DeviceDiagnosticReport(**payload)
        
        sn = payload.get("sensor_sn") or payload.get("sn")
        ts_ms = payload.get("ts_ms")
        
        # 2. Write Metadata to MySQL (diagnosis_record)
        context = await DiagnosisContextService.get_by_sn_managed(sn)
        if context:
            record = await DiagnosisRecordService.create_managed(
                report_id=report.report_id,
                sn=sn,
                report_ts=ts_ms,
                payload=payload,
                context=context,
            )
            if not record:
                logger.warning(f"Failed to create DiagnosisRecord for {path}")
        else:
            logger.warning(f"No context found for SN {sn}, skipping MySQL insert.")

        # 3. Write Time-series Data to InfluxDB
        from pub.manager.database import influxdb_manager
        from influxdb_client import Point
        from influxdb_client.client.write_api import SYNCHRONOUS
        import math

        client = influxdb_manager.get_client()
        write_api = client.write_api(write_options=SYNCHRONOUS)
        
        point = Point("vibration_feature") \
            .tag("sn", report.sensor_sn) \
            .tag("location_id", report.location_id or "") \
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
        
        await asyncio.to_thread(
            write_api.write,
            bucket=influxdb_manager.bucket,
            org=influxdb_manager.org,
            record=point,
        )
        
        # 4. Update TrendCache (72-hour rolling window for slope/amplitude calculation)
        from pub.services.trend_cache import TrendCacheService
        if report.location_id:
            metrics = {
                "rms_vel_mm_s": max_rms_vel,
            }
            if rms_m is not None:
                metrics["rms_acc_g"] = rms_m
            if report.temperature_c is not None:
                metrics["temperature"] = float(report.temperature_c)
            await TrendCacheService.push_metrics(report.location_id, report.ts_ms, metrics)

        # 5. Trigger Diagnosis
        # Publish downstream to diagnosis module via lightweight payload
        redis_client = redis_manager.get_client()
        trigger_payload = {
            "report_id": str(report.report_id),
            "schema_version": str(report.schema_version) if report.schema_version else "1.0",
            "sensor_sn": report.sensor_sn,
            "device_id": str(report.device_id),
            "temperature_c": str(report.temperature_c) if report.temperature_c is not None else "",
            "max_rms_vel": str(max_rms_vel),
            "task_id": str(report.task_id) if report.task_id else "",
            "delay": str(report.delay) if report.delay is not None else "0",
            "total": str(report.total),
            "sensor_id": str(report.sensor_id) if report.sensor_id else "",
            "location_id": str(report.location_id) if report.location_id else "",
            "tenant_id": str(report.tenant_id) if report.tenant_id else "",
            "region_id": str(report.region_id) if report.region_id else "",
            "device_category_id": str(report.device_category_id) if report.device_category_id else "",
            "process_device_id": str(report.process_device_id) if report.process_device_id else "",
            "ts_ms": str(report.ts_ms),
        }
        await asyncio.to_thread(
            redis_client.xadd,
            REDIS_STREAM_DIAGNOSIS_TRIGGER,
            trigger_payload,
            maxlen=settings.stream_maxlen,
            approximate=True,
        )
        
        logger.debug(f"Persisted {path} and triggered diagnosis stream.")
        return True
    except Exception as e:
        logger.error(f"Error processing message {path}: {e}", exc_info=True)
        return False

async def _worker_loop(worker_id: int):
    redis_client = redis_manager.get_client()
    stream = REDIS_STREAM_PERSISTENCE_INGEST
    group = REDIS_STREAM_PERSISTENCE_GROUP
    consumer = f"worker-{worker_id}-{uuid.uuid4().hex[:8]}"
    
    # Initialize Stream & Group
    try:
        await asyncio.to_thread(redis_client.xgroup_create, stream, group, id='0', mkstream=True)
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            logger.error(f"Failed to create consumer group: {e}")
            
    logger.info(f"Persistence Stream Worker {consumer} started.")
    
    while True:
        try:
            messages = await asyncio.to_thread(
                redis_client.xreadgroup,
                group,
                consumer,
                {stream: '>'},
                count=settings.stream_worker_batch_size,
                block=settings.stream_block_ms
            )
            
            if not messages:
                continue
                
            for stream_name, msg_list in messages:
                for message_id, msg_data in msg_list:
                    bucket = msg_data.get("bucket")
                    path = msg_data.get("path")
                    if isinstance(bucket, bytes):
                        bucket = bucket.decode("utf-8")
                    if isinstance(path, bytes):
                        path = path.decode("utf-8")
                        
                    success = await _process_stream_message(bucket, path)
                    if success:
                        await asyncio.to_thread(redis_client.xack, stream, group, message_id)
        except asyncio.CancelledError:
            logger.info(f"Worker {consumer} cancelled.")
            break
        except Exception as e:
            logger.error(f"Worker {consumer} error: {e}")
            await asyncio.sleep(1)

async def start_stream_workers(count: int = 3):
    for i in range(count):
        task = asyncio.create_task(_worker_loop(i))
        _workers.append(task)

async def stop_stream_workers():
    for task in _workers:
        task.cancel()
    if _workers:
        await asyncio.gather(*_workers, return_exceptions=True)
    _workers.clear()

import asyncio
import json
import time
import uuid

import redis as redis_lib
from sqlalchemy import select

from pub.manager.database import db_manager, minio_manager, redis_manager, influxdb_manager
import logging
from pub.utils.redis_keys import (
    REDIS_KEY_PERSISTENCE_PROCESSED_REPORT,
    REDIS_KEY_PERSISTENCE_PROCESSING_REPORT,
    REDIS_STREAM_PERSISTENCE_INGEST,
    REDIS_STREAM_PERSISTENCE_GROUP,
    REDIS_STREAM_DIAGNOSIS_TRIGGER,
)
from pub.services.diagnosis.diagnosis_context_service import DiagnosisContextService
from pub.services.diagnosis.diagnosis_record_service import DiagnosisRecordService
from pub.models.diagnosis import DiagnosisRecord
from pub.models.report import DeviceDiagnosticReport

from app.config import settings

logger = logging.getLogger("persistence-stream")
_workers = []
_PROCESSING_LOCK_TTL_SECONDS = 300
_PROCESSED_TTL_SECONDS = 30 * 24 * 3600
_PENDING_MIN_IDLE_MS = 60_000
_PENDING_SCAN_INTERVAL_SECONDS = 30


async def _diagnosis_record_exists(report_id: str) -> bool:
    async with db_manager.SessionLocal() as session:
        statement = select(DiagnosisRecord.id).where(
            DiagnosisRecord.id == uuid.UUID(report_id)
        )
        return (await session.execute(statement)).scalar_one_or_none() is not None


def _create_worker_redis() -> redis_lib.Redis:
    """为 stream worker 创建独立 Redis 连接。

    xreadgroup 的 block 参数会长期占用 socket，必须与全局业务连接（redis_manager）隔离。
    socket_timeout 设置为 block_ms + 3000ms，确保不会因超时误断阻塞等待。
    """
    socket_timeout = (settings.stream_block_ms / 1000) + 3.0
    return redis_lib.from_url(
        settings.stream_redis_url,
        decode_responses=True,
        socket_timeout=socket_timeout,
        socket_connect_timeout=3.0,
        retry_on_timeout=True,
        health_check_interval=30,
    )

async def _process_stream_message(bucket: str, path: str) -> bool:
    redis_client = redis_manager.get_client()
    processing_lock_key = None
    lock_acquired = False
    try:
        # 1. Fetch JSON from MinIO
        from pub.clients.minio import download_json_from_minio_sync
        payload = await asyncio.to_thread(
            download_json_from_minio_sync,
            minio_manager.get_client(),
            bucket,
            path
        )
        if not payload:
            logger.error(f"Failed to fetch {path} from MinIO")
            return False
        report = DeviceDiagnosticReport(**payload)

        processed_key = REDIS_KEY_PERSISTENCE_PROCESSED_REPORT.format(
            report_id=report.report_id
        )
        if await asyncio.to_thread(redis_client.exists, processed_key):
            logger.info("Skipping already persisted report_id=%s", report.report_id)
            return True

        processing_lock_key = REDIS_KEY_PERSISTENCE_PROCESSING_REPORT.format(
            report_id=report.report_id
        )
        lock_acquired = bool(
            await asyncio.to_thread(
                redis_client.set,
                processing_lock_key,
                "1",
                nx=True,
                ex=_PROCESSING_LOCK_TTL_SECONDS,
            )
        )
        if not lock_acquired:
            logger.info("Report is already being persisted: report_id=%s", report.report_id)
            return False
        
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
                # A retry after MySQL commit is safe: the report UUID already
                # exists. A genuine write failure must not be acknowledged.
                if not await _diagnosis_record_exists(str(report.report_id)):
                    logger.error("Failed to persist DiagnosisRecord for %s", path)
                    return False
                logger.info(
                    "DiagnosisRecord already exists for report_id=%s",
                    report.report_id,
                )
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

        if report.bearing_features is not None:
            for axis in ("X", "Y", "Z"):
                axis_features = getattr(report.bearing_features, axis)
                axis_name = axis.lower()
                if axis_features.status != 0:
                    continue
                if axis_features.envelope_kurtosis is not None:
                    point = point.field(
                        f"bearing_envelope_kurtosis_{axis_name}",
                        float(axis_features.envelope_kurtosis),
                    )
                for fault_code in ("bpfo", "bpfi", "bsf", "ftf"):
                    candidates = getattr(
                        axis_features.fault_candidates,
                        fault_code,
                    )
                    if candidates:
                        point = point.field(
                            f"bearing_{fault_code}_max_snr_{axis_name}",
                            float(max(item.snr_db for item in candidates)),
                        )
        
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
                metrics["temperature_c"] = float(report.temperature_c)
            await TrendCacheService.push_metrics(report.location_id, report.ts_ms, metrics)

        # 5. Trigger Diagnosis
        # Publish downstream to diagnosis module via lightweight payload
        trigger_payload = {
            "report_id": str(report.report_id),
            "schema_version": str(report.schema_version) if report.schema_version else "1.0",
            "sensor_sn": report.sensor_sn,
            "device_id": str(report.device_id),
            "temperature_c": str(report.temperature_c) if report.temperature_c is not None else "",
            "max_rms_vel": str(max_rms_vel),
            "fs_hz": str(report.fs_hz) if report.fs_hz is not None else "",
            "points": str(report.points) if report.points is not None else "",
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
            "bearing_features": (
                json.dumps(
                    report.bearing_features.model_dump(mode="json"),
                    separators=(",", ":"),
                )
                if report.bearing_features is not None
                else ""
            ),
        }
        await asyncio.to_thread(
            redis_client.xadd,
            REDIS_STREAM_DIAGNOSIS_TRIGGER,
            trigger_payload,
            maxlen=settings.stream_maxlen,
            approximate=True,
        )
        await asyncio.to_thread(
            redis_client.set,
            processed_key,
            "1",
            ex=_PROCESSED_TTL_SECONDS,
        )
        
        logger.debug(f"Persisted {path} and triggered diagnosis stream.")
        return True
    except Exception as e:
        logger.error(f"Error processing message {path}: {e}", exc_info=True)
        return False
    finally:
        if lock_acquired and processing_lock_key:
            try:
                await asyncio.to_thread(redis_client.delete, processing_lock_key)
            except Exception:
                logger.warning(
                    "Failed to release persistence lock for %s",
                    processing_lock_key,
                    exc_info=True,
                )


async def _claim_stale_messages(redis_client, group: str, consumer: str):
    """Claim server-accepted messages left pending by a failed or dead worker."""
    result = await asyncio.to_thread(
        redis_client.xautoclaim,
        REDIS_STREAM_PERSISTENCE_INGEST,
        group,
        consumer,
        _PENDING_MIN_IDLE_MS,
        "0-0",
        count=settings.stream_worker_batch_size,
    )
    return result[1] if result and len(result) > 1 else []

async def _worker_loop(worker_id: int):
    redis_client = _create_worker_redis()  # 独立连接，不复用全局 redis_manager
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
    last_pending_scan = 0.0

    while True:
        try:
            messages = []
            now = time.monotonic()
            if now - last_pending_scan >= _PENDING_SCAN_INTERVAL_SECONDS:
                stale_messages = await _claim_stale_messages(redis_client, group, consumer)
                messages = [(stream, stale_messages)] if stale_messages else []
                last_pending_scan = now

            if not messages:
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

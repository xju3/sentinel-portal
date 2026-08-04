"""
Sensor management endpoints
"""

import logging
import json
import io
import math
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Path, BackgroundTasks, Body, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated, cast, List, Literal, Optional
from uuid import UUID, uuid4
import asyncio
from app.config import settings

logger = logging.getLogger(__name__)


from pub.services import get_session
from pub.services import DiagnosisRecordService
from pub.services import DiagnosisContextService
from pub.services import SensorTypeService, SensorDbService, SensorBatchService, SensorConfigService
from pub.services import dispatch_quick_diagnosis_tasks
from pub.services import (
    FFT_COLLECTION_ACTION,
    SensorCommunicationService,
    SYSTEM_ACTION_CONFIG_UPDATE,
    complete_device_system_task,
    create_manual_sensor_task,
    dispatch_pending_sensor_tasks,
    list_sensor_tasks,
    record_sensor_status,
)
from pub.models.customer import Account
from pub.models.report import BearingFeatures
from pub.models.sensor import Sensor, SensorBatch, SensorTask
from pub.exceptions.domain_exception import DomainException
from pub.decorators.dashboard_cache import rebuild_dashboard_cache

from app.utils.auth import get_current_account
from app.utils.response import success
from app.database import minio_manager, redis_manager, stream_redis_manager
from pub.utils.redis_keys import (
    REDIS_KEY_DASHBOARD_HEALTH_DIRTY,
    REDIS_KEY_SENSOR_META,
)
from app.clients.mqtt import api_mqtt_manager
from pub.clients.minio import upload_json_to_minio_sync
from pub.contract.sensors import (
    SensorTypeCreate,
    SensorTypeUpdate,
    SensorTypeResponse,
    SensorBatchCreate,
    SensorBatchUpdate,
    SensorBatchResponse,
    SensorCreate,
    SensorUpdate,
    SensorResponse,
    PagedSensorResponse,
    SensorTaskCreate,
    SensorTaskResponse,
    PagedSensorTaskResponse,
    SensorStatusCreate,
    SensorStatusResponse,
    SensorBindingResponse,
)

router = APIRouter(prefix="/sensors", tags=["sensors"])
device_router = APIRouter(prefix="/sensors", tags=["sensors"])


# ==========================================
# 1. SensorType
# ==========================================
@router.get("/types")
async def list_sensor_types(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    session: AsyncSession = Depends(get_session),
):
    return success(await SensorTypeService.get_all(session, skip, limit, sort_by, sort_order))


@router.get("/types/{obj_id}")
async def get_sensor_type(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    obj = await SensorTypeService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="SensorType not found")
    return success(obj)


@router.post("/types")
@rebuild_dashboard_cache()
async def create_sensor_type(
    item: SensorTypeCreate,
    session: AsyncSession = Depends(get_session),
):
    return success(await SensorTypeService.create(session, item.model_dump()))


@router.put("/types/{obj_id}")
@rebuild_dashboard_cache()
async def update_sensor_type(
    obj_id: UUID,
    item: SensorTypeUpdate,
    session: AsyncSession = Depends(get_session),
):
    db_obj = await SensorTypeService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorType not found")

    update_data = item.model_dump(exclude_unset=True)
    return success(await SensorTypeService.update(session, db_obj, update_data))


@router.delete("/types/{obj_id}")
@rebuild_dashboard_cache()
async def delete_sensor_type(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    db_obj = await SensorTypeService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorType not found")

    await SensorTypeService.delete(session, db_obj)
    return success({"message": "SensorType deleted successfully"})


# ==========================================
# 2. SensorBatch (defined before Sensor to avoid path conflict with /{obj_id})
# ==========================================
@router.get("/batches")
async def list_sensor_batches(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    stmt = select(SensorBatch).where(SensorBatch.tenant_id == current_account.tenant_id)
    if sort_by and hasattr(SensorBatch, sort_by):
        col = getattr(SensorBatch, sort_by)
        stmt = stmt.order_by(col.desc() if sort_order == "descend" else col.asc())
    else:
        stmt = stmt.order_by(SensorBatch.created_at.desc())

    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    items = (await session.execute(stmt.offset(skip).limit(limit))).scalars().all()
    return success({"items": items, "total": total})

@router.get("/batches/{obj_id}")
async def get_sensor_batch(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    obj = await SensorBatchService.get_by_id_and_tenant(session, obj_id, cast(UUID, current_account.tenant_id))
    if not obj:
        raise HTTPException(status_code=404, detail="SensorBatch not found")
    return success(obj)


@router.post("/batches")
@rebuild_dashboard_cache()
async def create_sensor_batch(
    item: SensorBatchCreate,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    data = item.model_dump()
    data["tenant_id"] = cast(UUID, current_account.tenant_id)
    return success(await SensorBatchService.create(session, data))


@router.put("/batches/{obj_id}")
@rebuild_dashboard_cache()
async def update_sensor_batch(
    obj_id: UUID,
    item: SensorBatchUpdate,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    db_obj = await SensorBatchService.get_by_id_and_tenant(session, obj_id, cast(UUID, current_account.tenant_id))
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorBatch not found")

    update_data = item.model_dump(exclude_unset=True)
    return success(await SensorBatchService.update(session, db_obj, update_data, background_tasks))


@router.delete("/batches/{obj_id}")
@rebuild_dashboard_cache()
async def delete_sensor_batch(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    db_obj = await SensorBatchService.get_by_id_and_tenant(session, obj_id, cast(UUID, current_account.tenant_id))
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorBatch not found")

    await SensorBatchService.delete(session, db_obj)
    return success({"message": "SensorBatch deleted successfully"})


# ==========================================
# 3. Sensor
# ==========================================
@router.get("/binding/{sn}")
async def get_sensor_binding(
    sn: str,
    session: AsyncSession = Depends(get_session),
):
    binding = await SensorDbService.get_binding_by_sn(session, sn)
    
    meta_data = await SensorDbService.get_sensor_metadata_for_cache(session, sn)
    if meta_data:
        redis_client = redis_manager.get_client()
        if redis_client:
            redis_client.set(REDIS_KEY_SENSOR_META.format(sn=sn), json.dumps(meta_data))

    return success(SensorBindingResponse(**binding) if binding else SensorBindingResponse())


@router.get("")
async def list_sensors(
    current: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    session: AsyncSession = Depends(get_session),
):
    items, total = await SensorDbService.get_paged(session, current, pageSize, keyword, sort_by, sort_order)
    return success(PagedSensorResponse(items=items, total=total))


@router.get("/by-batch/{batch_id}")
async def list_sensors_by_batch(
    batch_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    # Verify the batch belongs to the current tenant
    batch = await SensorBatchService.get_by_id_and_tenant(session, batch_id, cast(UUID, current_account.tenant_id))
    if not batch:
        raise HTTPException(status_code=404, detail="SensorBatch not found")
    return success(await SensorDbService.get_by_batch_id(session, batch_id, skip, limit, sort_by, sort_order))


@router.get("/tasks")
async def list_sensor_tasks_for_admin(
    current: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    status: Optional[Literal[0, 1, 2]] = Query(None),
    session: AsyncSession = Depends(get_session),
    _current_account: Account = Depends(get_current_account),
):
    items, total = await list_sensor_tasks(
        session=session,
        current=current,
        page_size=pageSize,
        keyword=keyword,
        status=status,
    )
    return success(PagedSensorTaskResponse(items=items, total=total))


@router.post("/tasks")
async def create_sensor_task_for_admin(
    item: SensorTaskCreate,
    session: AsyncSession = Depends(get_session),
    _current_account: Account = Depends(get_current_account),
):
    try:
        task = await create_manual_sensor_task(session=session, **item.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success(SensorTaskResponse.model_validate(task))


@router.post("/{task_id}/complete/{status}")
@device_router.post("/{task_id}/complete/{status}")
# Compatibility for deployed firmware that reports completion with GET.
# Keep it out of OpenAPI so new integrations continue to use POST.
@router.get("/{task_id}/complete/{status}", include_in_schema=False)
@device_router.get("/{task_id}/complete/{status}", include_in_schema=False)
async def complete_sensor_system_task(
    task_id: UUID,
    status: Annotated[int, Path(ge=0, le=1)],
    session: AsyncSession = Depends(get_session),
):
    task = await complete_device_system_task(
        session=session,
        task_id=task_id,
        success=(status == 1),
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found or not dispatchable by device")
    return success(SensorTaskResponse.model_validate(task))


@router.get("/tasks/{sn}")
async def list_sensor_tasks_by_sn(
    sn: str,
    session: AsyncSession = Depends(get_session),
):
    return await dispatch_pending_sensor_tasks(session, sn)


@router.get("/config/{task_id}")
async def get_sensor_config_by_task(
    task_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(SensorTask).where(SensorTask.id == task_id)
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Sensor task not found")
    if task.action != SYSTEM_ACTION_CONFIG_UPDATE:
        raise HTTPException(status_code=400, detail="Task is not a config update")
    config = await SensorConfigService.get_config_by_sn(session, task.sn)
    if config is None:
        raise HTTPException(status_code=404, detail="Sensor config not found")

    return config


@router.get("/{sn}/config")
async def get_sensor_config_by_sn(
    sn: str,
    session: AsyncSession = Depends(get_session),
):
    config = await SensorConfigService.get_config_by_sn(session, sn)
    if config is None:
        raise HTTPException(status_code=404, detail="Sensor config not found")

    return config


@router.post("/status")
async def receive_sensor_status(
    item: SensorStatusCreate,
    session: AsyncSession = Depends(get_session),
):
    try:
        status = await record_sensor_status(session=session, **item.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success(SensorStatusResponse.model_validate(status))


@router.get("/{obj_id}")
async def get_sensor(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    obj = await SensorDbService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return success(obj)


@router.post("")
@rebuild_dashboard_cache()
async def create_sensor(
    item: SensorCreate,
    session: AsyncSession = Depends(get_session),
):
    return success(await SensorDbService.create(session, item.model_dump()))


@router.put("/{obj_id}")
@rebuild_dashboard_cache()
async def update_sensor(
    obj_id: UUID,
    item: SensorUpdate,
    session: AsyncSession = Depends(get_session),
):
    db_obj = await SensorDbService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Sensor not found")

    update_data = item.model_dump(exclude_unset=True)
    return success(await SensorDbService.update(session, db_obj, update_data))


@router.delete("/{obj_id}")
@rebuild_dashboard_cache()
async def delete_sensor(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    db_obj = await SensorDbService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Sensor not found")

    await SensorDbService.delete(session, db_obj)
    return success({"message": "Sensor deleted successfully"})


# ==========================================
# 4. Data Collection Endpoint
# ==========================================
def _process_sensor_data_background(object_name: str, payload: dict):
    # Backward compatibility stub, now implemented in async function below
    pass

async def _process_sensor_data_background_async(object_name: str, payload: dict, report_id: str, total: int = 0):
    """Background task to upload data to MinIO, create DiagnosisRecord, and notify via MQTT"""
    # Receiving a valid report is itself proof that the sensor is online.
    # Keep communication_state independent from MinIO/diagnosis success so the
    # dashboard does not mark an actively reporting sensor as offline.
    try:
        communication = await SensorCommunicationService.record_from_payload_managed(
            payload
        )
        tenant_id = payload.get("tenant_id")
        if communication is not None and tenant_id:
            redis_client = redis_manager.get_client()
            if redis_client:
                await asyncio.to_thread(
                    redis_client.hset,
                    REDIS_KEY_DASHBOARD_HEALTH_DIRTY,
                    str(tenant_id),
                    int(datetime.now(timezone.utc).timestamp() * 1000),
                )
    except Exception as err:
        logger.error(
            "Failed to update communication state for %s: %s",
            payload.get("sensor_sn") or payload.get("sn"),
            err,
            exc_info=True,
        )

    # 1. 调用通用的 MinIO 上传工具 (在线程池中执行防止阻塞)
    success = await asyncio.to_thread(
        upload_json_to_minio_sync,
        minio_client=minio_manager.client,
        bucket_name="json",
        object_name=object_name,
        payload=payload
    )
    
    if success:
        # 2. 存入 MinIO 后，将事件压入 Redis Stream，交由 persistence 服务进行数据持久化
        try:
            from pub.utils.redis_keys import REDIS_STREAM_PERSISTENCE_INGEST
            
            redis_client = stream_redis_manager.get_client()
            await asyncio.to_thread(
                redis_client.xadd,
                REDIS_STREAM_PERSISTENCE_INGEST,
                {"bucket": "json", "path": object_name},
                maxlen=5000,
                approximate=True,
            )
            logger.info(f"Published to Redis Stream '{REDIS_STREAM_PERSISTENCE_INGEST}' for {object_name}")
        except Exception as err:
            logger.error(f"Failed to publish to Redis Stream for {object_name}: {err}")
            
        # 3. Notify via MQTT (for diagnosis service and others)
        try:
            mqtt_payload = json.dumps({"bucket": "json", "path": object_name})
            api_mqtt_manager.publish(settings.mqtt_topic, mqtt_payload)
            logger.info(f"Published to MQTT '{settings.mqtt_topic}' for {object_name}")
        except Exception as err:
            logger.error(f"Failed to publish to MQTT for {object_name}: {err}")
    else:
        logger.error(f"Failed to upload data to MinIO for {object_name}")


@router.post("/data")
async def receive_sensor_data(
    background_tasks: BackgroundTasks,
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_session),
):
    """Receive processed sensor data and asynchronously store to MinIO"""
    sn = payload.get("sensor_sn") or payload.get("sn")
    delay = payload.get("delay", 0)
    period = payload.get("period")
    total = payload.get("total", 0)

    if not sn:
        raise HTTPException(status_code=400, detail="Missing 'sn' in payload")

    if payload.get("bearing_features") is not None:
        try:
            BearingFeatures.model_validate(payload["bearing_features"])
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid 'bearing_features': {exc}",
            ) from exc

    if (
        isinstance(delay, bool)
        or not isinstance(delay, (int, float))
        or not math.isfinite(delay)
        or delay < 0
    ):
        raise HTTPException(status_code=400, detail="'delay' must be a non-negative number")

    if delay > 0 and (
        isinstance(period, bool)
        or not isinstance(period, (int, float))
        or not math.isfinite(period)
        or period <= 0
    ):
        raise HTTPException(
            status_code=400,
            detail="'period' must be a positive number of minutes for backfilled data",
        )

    try:
        dt_utc = datetime.now(timezone.utc)
        if delay > 0:
            dt_utc -= timedelta(minutes=delay * period)

        ts_ms = int(dt_utc.timestamp() * 1000)
        tz_utc_8 = timezone(timedelta(hours=8))
        dt_utc8 = dt_utc.astimezone(tz_utc_8)

        # Format paths: {sn}/{YYYY}/{MM}/{DD}/{HH}-{mm}-{ss}.json
        object_name = f"{sn}/{dt_utc8.strftime('%Y/%m/%d/%H-%M-%S')}.json"

        # 优先使用 payload 中自带的 report_id (如 result.json 中提供的)，如果没有再兜底生成
        report_id = payload.get("report_id") or str(uuid4())
        stored_payload = dict(payload)
        
        if "sn" in stored_payload:
            del stored_payload["sn"]
        stored_payload["sensor_sn"] = sn
        
        meta: dict | None = None
        redis_client = redis_manager.get_client()
        if delay > 0:
            # A delayed report must use the binding that was effective at its
            # sampling time, never the sensor's current binding cache.
            meta = await SensorDbService.get_sensor_metadata_for_cache(
                session,
                str(sn),
                sampled_at_ms=ts_ms,
            )
        elif redis_client:
            meta_str = redis_client.get(REDIS_KEY_SENSOR_META.format(sn=sn))
            if not meta_str:
                meta_data = await SensorDbService.get_sensor_metadata_for_cache(
                    session,
                    str(sn),
                )
                if meta_data:
                    meta_str = json.dumps(meta_data)
                    redis_client.set(REDIS_KEY_SENSOR_META.format(sn=sn), meta_str)
            if meta_str:
                try:
                    meta = json.loads(meta_str)
                except Exception as e:
                    logger.error(f"Failed to parse sensor metadata from redis for {sn}: {e}")
        else:
            meta = await SensorDbService.get_sensor_metadata_for_cache(
                session,
                str(sn),
            )

        if meta:
            # Binding identity is server-owned. Overwrite any stale binding
            # profile carried by the device, especially for delayed reports.
            for key, value in meta.items():
                stored_payload[key] = value

        stored_payload["ts_ms"] = ts_ms
        stored_payload["report_id"] = report_id

        tasks: list[dict] = []
        try:
            tasks = await dispatch_quick_diagnosis_tasks(
                session=session,
                report_id=report_id,
                sn=str(sn),
                payload=stored_payload,
            )
        except Exception as quick_err:
            logger.error(
                "Failed to dispatch quick diagnosis tasks for sn=%s report_id=%s: %s",
                sn,
                report_id,
                quick_err,
                exc_info=True,
            )
            raise HTTPException(
                status_code=503,
                detail="Task decision unavailable; retry this upload",
            ) from quick_err

        # Add to background tasks to execute immediately after returning response
        background_tasks.add_task(_process_sensor_data_background_async, object_name, stored_payload, report_id, total)

        return success(tasks)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing sensor data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error processing data")

@router.post("/tasks/{task_id}/fft")
async def upload_sensor_fft_data(
    task_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    task = await session.get(SensorTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="FFT task not found")
    if task.action != FFT_COLLECTION_ACTION:
        raise HTTPException(status_code=409, detail="Task is not FFT action 99")

    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty payload")

    client = minio_manager.get_client()
    try:
        client.put_object(
            bucket_name=minio_manager.bucket_name,
            object_name=str(task_id),
            data=io.BytesIO(body),
            length=len(body),
            content_type="application/octet-stream",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to MinIO: {str(e)}")

    from pub.utils.redis_keys import REDIS_STREAM_FFT_TRIGGER

    redis_client = stream_redis_manager.get_client()
    try:
        await asyncio.to_thread(
            redis_client.xadd,
            REDIS_STREAM_FFT_TRIGGER,
            {"task_id": str(task_id)},
        )
    except Exception as exc:
        logger.error(
            "FFT file stored but diagnosis trigger failed: task_id=%s",
            task_id,
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="FFT stored but diagnosis notification failed; retry upload",
        ) from exc

    return success({"message": "FFT data uploaded successfully"})

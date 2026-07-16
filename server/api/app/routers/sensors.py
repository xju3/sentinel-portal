"""
Sensor management endpoints
"""

import logging
import json
import io
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Body, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import cast, List, Literal, Optional
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
    SYSTEM_ACTION_CONFIG_UPDATE,
    complete_device_system_task,
    create_manual_sensor_task,
    dispatch_pending_sensor_tasks,
    list_sensor_tasks,
    record_sensor_status,
)
from pub.models.customer import Account
from pub.models.sensor import Sensor, SensorBatch, SensorTask
from pub.exceptions.domain_exception import DomainException
from pub.decorators.dashboard_cache import rebuild_dashboard_cache

from app.utils.auth import get_current_account
from app.utils.response import success
from app.database import minio_manager
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
    SensorTaskCompleteRequest,
    SensorStatusCreate,
    SensorStatusResponse,
)

router = APIRouter(prefix="/sensors", tags=["sensors"])


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


@router.post("/tasks/{task_id}/complete/{status}")
async def complete_sensor_system_task(
    task_id: UUID,
    status: int,
    item: SensorTaskCompleteRequest,
    session: AsyncSession = Depends(get_session),
):
    task = await complete_device_system_task(
        session=session,
        task_id=task_id,
        sn=item.sn,
        success=(status == 0),
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

async def _process_sensor_data_background_async(object_name: str, payload: dict, report_id: str):
    """Background task to upload data to MinIO, create DiagnosisRecord, and notify via MQTT"""
    # 1. 调用通用的 MinIO 上传工具 (在线程池中执行防止阻塞)
    success = await asyncio.to_thread(
        upload_json_to_minio_sync,
        minio_client=minio_manager.client,
        bucket_name="json",
        object_name=object_name,
        payload=payload
    )
    
    if success:
        # 2. 存入 MinIO 后，异步建档 (DiagnosisRecord)
        sn = payload.get("sn")
        ts_ms = payload.get("ts_ms")
        try:
            # 获取拓扑上下文
            context = await DiagnosisContextService.get_by_sn_managed(sn)
            record = await DiagnosisRecordService.create_managed(
                report_id=report_id,
                sn=sn,
                report_ts=ts_ms,
                payload=payload,
                context=context,
            )
            if not record:
                logger.warning(f"Failed to create DiagnosisRecord in background for {object_name}")
                return
                
            if record.quality_status == 1:
                logger.info(f"Data quality for {object_name} is unusable, skipping DIA trigger.")
                return
        except Exception as db_err:
            logger.error(f"Failed to create DiagnosisRecord for {object_name}: {db_err}")
            return

        # 3. 建档彻底落库后，执行业务强相关的 MQTT 通知，触发 DIA 计算
        try:
            mqtt_payload = json.dumps({"bucket": "json", "path": object_name})
            if await asyncio.to_thread(api_mqtt_manager.publish, settings.mqtt_topic, mqtt_payload):
                logger.info(f"Published to MQTT topic '{settings.mqtt_topic}': {mqtt_payload}")
        except Exception as mqtt_err:
            logger.error(f"Failed to publish MQTT message for {object_name}: {mqtt_err}")
    else:
        logger.error(f"Failed to upload data to MinIO for {object_name}")


@router.post("/data")
async def receive_sensor_data(
    background_tasks: BackgroundTasks,
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_session),
):
    """Receive processed sensor data and asynchronously store to MinIO"""
    sn = payload.get("sn")
    seq = payload.get("seq", 0)

    if not sn:
        raise HTTPException(status_code=400, detail="Missing 'sn' in payload")
    if type(seq) is not int or seq < 0:
        raise HTTPException(status_code=400, detail="'seq' must be a non-negative integer")

    try:
        # The newest sample uses receive time. Backlogged samples are spaced by
        # the sensor's configured patrol interval, loaded through the existing
        # per-SN Redis read-through cache.
        dt_utc = datetime.now(timezone.utc)
        if seq > 0:
            context = await DiagnosisContextService.get_by_sn(session, str(sn))
            health_check = context.get("health_check") if context else None
            patrol = health_check.get("patrol") if health_check else None
            try:
                patrol_minutes = float(patrol)
            except (TypeError, ValueError):
                patrol_minutes = 0
            if patrol_minutes <= 0:
                logger.warning(f"Patrol frequency is not configured for sensor '{sn}'")
                patrol_minutes = 0
            dt_utc -= timedelta(minutes=patrol_minutes * seq)

        ts_ms = int(dt_utc.timestamp() * 1000)
        tz_utc_8 = timezone(timedelta(hours=8))
        dt_utc8 = dt_utc.astimezone(tz_utc_8)

        # Format paths: {sn}/{YYYY}/{MM}/{DD}/{HH}-{mm}-{ss}.json
        object_name = f"{sn}/{dt_utc8.strftime('%Y/%m/%d/%H-%M-%S')}.json"

        # 优先使用 payload 中自带的 report_id (如 result.json 中提供的)，如果没有再兜底生成
        report_id = payload.get("report_id") or str(uuid4())
        stored_payload = dict(payload)
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

        # Add to background tasks to execute immediately after returning response
        background_tasks.add_task(_process_sensor_data_background_async, object_name, stored_payload, report_id)

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
    background_tasks: BackgroundTasks,
):
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty payload")

    client = minio_manager.get_client()
    try:
        client.put_object(
            bucket_name="fft",
            object_name=str(task_id),
            data=io.BytesIO(body),
            length=len(body),
            content_type="application/octet-stream",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to MinIO: {str(e)}")

    from pub.services import process_fft_metadata_background
    background_tasks.add_task(process_fft_metadata_background, task_id)

    return success({"message": "FFT data uploaded successfully"})

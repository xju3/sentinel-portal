"""
Sensor management endpoints
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


from app.services.dependencies import get_session
from app.services.sensor_service import SensorTypeService, SensorDbService, SensorBatchService
from app.models.customer import Account
from app.models.sensor import Sensor
from app.utils.auth import get_current_account
from app.utils.response import success
from app.contract.sensors import (
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
)

router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.get("/types")
async def list_sensor_types(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    return success(await SensorTypeService.get_all(session, skip, limit))


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
async def create_sensor_type(
    item: SensorTypeCreate,
    session: AsyncSession = Depends(get_session),
):
    return success(await SensorTypeService.create(session, item.model_dump()))


@router.put("/types/{obj_id}")
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
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    return success(await SensorBatchService.get_by_tenant(session, current_account.tenant_id, skip, limit))


@router.get("/batches/{obj_id}")
async def get_sensor_batch(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    obj = await SensorBatchService.get_by_id_and_tenant(session, obj_id, current_account.tenant_id)
    if not obj:
        raise HTTPException(status_code=404, detail="SensorBatch not found")
    return success(obj)


@router.post("/batches")
async def create_sensor_batch(
    item: SensorBatchCreate,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    data = item.model_dump()
    data["tenant_id"] = current_account.tenant_id
    return success(await SensorBatchService.create(session, data))


@router.put("/batches/{obj_id}")
async def update_sensor_batch(
    obj_id: UUID,
    item: SensorBatchUpdate,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    db_obj = await SensorBatchService.get_by_id_and_tenant(session, obj_id, current_account.tenant_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorBatch not found")

    update_data = item.model_dump(exclude_unset=True)

    try:
        return success(await SensorBatchService.update(session, db_obj, update_data))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



@router.delete("/batches/{obj_id}")
async def delete_sensor_batch(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    db_obj = await SensorBatchService.get_by_id_and_tenant(session, obj_id, current_account.tenant_id)
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
    session: AsyncSession = Depends(get_session),
):
    items, total = await SensorDbService.get_paged(session, current, pageSize, keyword)
    return success(PagedSensorResponse(items=items, total=total))


@router.get("/by-batch/{batch_id}")
async def list_sensors_by_batch(
    batch_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    # Verify the batch belongs to the current tenant
    batch = await SensorBatchService.get_by_id_and_tenant(session, batch_id, current_account.tenant_id)
    if not batch:
        raise HTTPException(status_code=404, detail="SensorBatch not found")
    return success(await SensorDbService.get_by_batch_id(session, batch_id, skip, limit))


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
async def create_sensor(
    item: SensorCreate,
    session: AsyncSession = Depends(get_session),
):
    return success(await SensorDbService.create(session, item.model_dump()))


@router.put("/{obj_id}")
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
async def delete_sensor(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    db_obj = await SensorDbService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Sensor not found")

    await SensorDbService.delete(session, db_obj)
    return success({"message": "Sensor deleted successfully"})

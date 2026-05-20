"""
Sensor management endpoints
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from uuid import UUID

logger = logging.getLogger(__name__)


from app.database import db_manager
from app.services.sensor_service import SensorTypeService, SensorDbService, SensorBatchService
from app.models.customer import Account
from app.models.sensor import Sensor
from app.utils.auth import get_current_account

router = APIRouter(prefix="/sensors", tags=["sensors"])


# ==========================================
# 1. SensorType
# ==========================================
class SensorTypeCreate(BaseModel):
    name: str
    battery: Optional[int] = 0
    network: Optional[int] = 1
    bluetooth: Optional[bool] = False
    description: Optional[str] = None


class SensorTypeUpdate(BaseModel):
    name: Optional[str] = None
    battery: Optional[int] = None
    network: Optional[int] = None
    bluetooth: Optional[bool] = None
    description: Optional[str] = None


class SensorTypeResponse(BaseModel):
    id: UUID
    name: str
    battery: int
    network: int
    bluetooth: bool
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


@router.get("/types", response_model=List[SensorTypeResponse])
async def list_sensor_types(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await SensorTypeService.get_all(session, skip, limit)


@router.get("/types/{obj_id}", response_model=SensorTypeResponse)
async def get_sensor_type(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    obj = await SensorTypeService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="SensorType not found")
    return obj


@router.post("/types", response_model=SensorTypeResponse)
async def create_sensor_type(
    item: SensorTypeCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await SensorTypeService.create(session, item.model_dump())


@router.put("/types/{obj_id}", response_model=SensorTypeResponse)
async def update_sensor_type(
    obj_id: UUID,
    item: SensorTypeUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await SensorTypeService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorType not found")

    update_data = item.model_dump(exclude_unset=True)
    return await SensorTypeService.update(session, db_obj, update_data)


@router.delete("/types/{obj_id}")
async def delete_sensor_type(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await SensorTypeService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorType not found")

    await SensorTypeService.delete(session, db_obj)
    return {"message": "SensorType deleted successfully"}


# ==========================================
# 2. SensorBatch (defined before Sensor to avoid path conflict with /{obj_id})
# ==========================================
class SensorBatchCreate(BaseModel):
    code: str
    qty: int
    sn: int
    status: int = 0
    description: Optional[str] = None
    sensor_type_id: UUID


class SensorBatchUpdate(BaseModel):
    code: Optional[str] = None
    qty: Optional[int] = None
    sn: Optional[int] = None
    status: Optional[int] = None
    description: Optional[str] = None
    sensor_type_id: Optional[UUID] = None


class SensorBatchResponse(BaseModel):
    id: UUID
    code: str
    qty: int
    sn: int
    status: int
    description: Optional[str] = None
    sensor_type_id: UUID
    tenant_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.get("/batches", response_model=List[SensorBatchResponse])
async def list_sensor_batches(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
    current_account: Account = Depends(get_current_account),
):
    return await SensorBatchService.get_by_tenant(session, current_account.tenant_id, skip, limit)


@router.get("/batches/{obj_id}", response_model=SensorBatchResponse)
async def get_sensor_batch(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
    current_account: Account = Depends(get_current_account),
):
    obj = await SensorBatchService.get_by_id_and_tenant(session, obj_id, current_account.tenant_id)
    if not obj:
        raise HTTPException(status_code=404, detail="SensorBatch not found")
    return obj


@router.post("/batches", response_model=SensorBatchResponse)
async def create_sensor_batch(
    item: SensorBatchCreate,
    session: AsyncSession = Depends(db_manager.get_session),
    current_account: Account = Depends(get_current_account),
):
    data = item.model_dump()
    data["tenant_id"] = current_account.tenant_id
    return await SensorBatchService.create(session, data)


@router.put("/batches/{obj_id}", response_model=SensorBatchResponse)
async def update_sensor_batch(
    obj_id: UUID,
    item: SensorBatchUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
    current_account: Account = Depends(get_current_account),
):
    db_obj = await SensorBatchService.get_by_id_and_tenant(session, obj_id, current_account.tenant_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorBatch not found")

    update_data = item.model_dump(exclude_unset=True)

    try:
        return await SensorBatchService.update(session, db_obj, update_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



@router.delete("/batches/{obj_id}")
async def delete_sensor_batch(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
    current_account: Account = Depends(get_current_account),
):
    db_obj = await SensorBatchService.get_by_id_and_tenant(session, obj_id, current_account.tenant_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorBatch not found")

    await SensorBatchService.delete(session, db_obj)
    return {"message": "SensorBatch deleted successfully"}


# ==========================================
# 3. Sensor
# ==========================================
class SensorCreate(BaseModel):
    sn: str
    description: Optional[str] = None
    active: Optional[bool] = True


class SensorUpdate(BaseModel):
    sn: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None


class SensorResponse(BaseModel):
    id: UUID
    sn: str
    description: Optional[str] = None
    active: bool
    active_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PagedSensorResponse(BaseModel):
    items: List[SensorResponse]
    total: int


@router.get("", response_model=PagedSensorResponse)
async def list_sensors(
    current: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    session: AsyncSession = Depends(db_manager.get_session),
):
    base_stmt = select(Sensor).order_by(Sensor.sn)
    if keyword:
        like = f"%{keyword}%"
        base_stmt = base_stmt.where(Sensor.sn.ilike(like))

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    count_result = await session.execute(count_stmt)
    total = count_result.scalar() or 0

    skip = (current - 1) * pageSize
    fetch_stmt = base_stmt.offset(skip).limit(pageSize)
    result = await session.execute(fetch_stmt)
    items = result.scalars().all()

    return PagedSensorResponse(items=items, total=total)


@router.get("/by-batch/{batch_id}", response_model=List[SensorResponse])
async def list_sensors_by_batch(
    batch_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
    current_account: Account = Depends(get_current_account),
):
    # Verify the batch belongs to the current tenant
    batch = await SensorBatchService.get_by_id_and_tenant(session, batch_id, current_account.tenant_id)
    if not batch:
        raise HTTPException(status_code=404, detail="SensorBatch not found")
    return await SensorDbService.get_by_batch_id(session, batch_id, skip, limit)


@router.get("/{obj_id}", response_model=SensorResponse)
async def get_sensor(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    obj = await SensorDbService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return obj


@router.post("", response_model=SensorResponse)
async def create_sensor(
    item: SensorCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await SensorDbService.create(session, item.model_dump())


@router.put("/{obj_id}", response_model=SensorResponse)
async def update_sensor(
    obj_id: UUID,
    item: SensorUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await SensorDbService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Sensor not found")

    update_data = item.model_dump(exclude_unset=True)
    return await SensorDbService.update(session, db_obj, update_data)


@router.delete("/{obj_id}")
async def delete_sensor(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await SensorDbService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Sensor not found")

    await SensorDbService.delete(session, db_obj)
    return {"message": "Sensor deleted successfully"}

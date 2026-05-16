"""
Sensor management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from uuid import UUID

from app.database import db_manager
from app.services.sensor_service import SensorTypeService, SensorDbService

router = APIRouter(prefix="/sensors", tags=["sensors"])


# ==========================================
# 1. SensorType
# ==========================================
class SensorTypeCreate(BaseModel):
    name: str
    battery_capacity: Optional[int] = 0
    network: Optional[int] = 1
    bluetooth: Optional[bool] = False
    description: Optional[str] = None


class SensorTypeUpdate(BaseModel):
    name: Optional[str] = None
    battery_capacity: Optional[int] = None
    network: Optional[int] = None
    bluetooth: Optional[bool] = None
    description: Optional[str] = None


class SensorTypeResponse(BaseModel):
    id: UUID
    name: str
    battery_capacity: int
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
# 2. Sensor
# ==========================================
class SensorCreate(BaseModel):
    sn: str
    description: Optional[str] = None
    battery: Optional[float] = 100.0
    active: Optional[bool] = True
    sensor_type_id: UUID


class SensorUpdate(BaseModel):
    sn: Optional[str] = None
    description: Optional[str] = None
    battery: Optional[float] = None
    active: Optional[bool] = None
    sensor_type_id: Optional[UUID] = None


class SensorResponse(BaseModel):
    id: UUID
    sn: str
    description: Optional[str] = None
    battery: float
    active: bool
    active_at: datetime
    created_at: datetime
    updated_at: datetime
    sensor_type_id: UUID

    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=List[SensorResponse])
async def list_sensors(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await SensorDbService.get_all(session, skip, limit)


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
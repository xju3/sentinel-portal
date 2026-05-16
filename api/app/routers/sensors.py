"""
Sensor management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel

from app.database import db_manager
from app.models.sensor import Sensor
from app.services.sensor_service import SensorService

router = APIRouter(prefix="/sensors", tags=["sensors"])


class SensorCreate(BaseModel):
    """Create sensor request model"""

    name: str
    sensor_type: str
    location: Optional[str] = None
    description: Optional[str] = None


class SensorUpdate(BaseModel):
    """Update sensor request model"""

    name: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SensorResponse(BaseModel):
    """Sensor response model"""

    id: int
    name: str
    sensor_type: str
    location: Optional[str] = None
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=List[SensorResponse])
async def list_sensors(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    """
    List all sensors with pagination
    """
    stmt = select(Sensor).offset(skip).limit(limit)
    result = await session.execute(stmt)
    sensors = result.scalars().all()
    return sensors


@router.get("/{sensor_id}", response_model=SensorResponse)
async def get_sensor(
    sensor_id: int,
    session: AsyncSession = Depends(db_manager.get_session),
):
    """
    Get sensor details by ID
    """
    stmt = select(Sensor).where(Sensor.id == sensor_id)
    result = await session.execute(stmt)
    sensor = result.scalar_one_or_none()

    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    return sensor


@router.post("", response_model=SensorResponse)
async def create_sensor(
    sensor: SensorCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    """
    Create a new sensor
    """
    db_sensor = Sensor(
        name=sensor.name,
        sensor_type=sensor.sensor_type,
        location=sensor.location,
        description=sensor.description,
    )
    session.add(db_sensor)
    await session.commit()
    await session.refresh(db_sensor)
    return db_sensor


@router.put("/{sensor_id}", response_model=SensorResponse)
async def update_sensor(
    sensor_id: int,
    sensor: SensorUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    """
    Update sensor information
    """
    stmt = select(Sensor).where(Sensor.id == sensor_id)
    result = await session.execute(stmt)
    db_sensor = result.scalar_one_or_none()

    if not db_sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    update_data = sensor.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_sensor, key, value)

    await session.commit()
    await session.refresh(db_sensor)
    return db_sensor


@router.delete("/{sensor_id}")
async def delete_sensor(
    sensor_id: int,
    session: AsyncSession = Depends(db_manager.get_session),
):
    """
    Delete a sensor
    """
    stmt = select(Sensor).where(Sensor.id == sensor_id)
    result = await session.execute(stmt)
    db_sensor = result.scalar_one_or_none()

    if not db_sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    await session.delete(db_sensor)
    await session.commit()
    return {"message": "Sensor deleted successfully"}
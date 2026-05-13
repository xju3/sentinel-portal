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
from app.models.sensor import Sensor, SensorReading
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


class SensorReadingCreate(BaseModel):
    """Create sensor reading request model"""
    value: float
    unit: str = "C"
    timestamp: Optional[datetime] = None


class SensorReadingResponse(BaseModel):
    """Sensor reading response model"""
    timestamp: datetime
    value: float
    unit: Optional[str] = None

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


@router.post("/{sensor_id}/readings")
async def add_sensor_reading(
    sensor_id: int,
    reading: SensorReadingCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    """
    Add a new reading for a specific sensor (stored in InfluxDB)
    """
    stmt = select(Sensor).where(Sensor.id == sensor_id)
    result = await session.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Sensor not found")

    success = SensorService.write_sensor_data(
        sensor_id=sensor_id,
        value=reading.value,
        unit=reading.unit,
        timestamp=reading.timestamp
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to write sensor data")
    return {"message": "Reading added successfully"}


@router.get("/{sensor_id}/readings", response_model=List[SensorReadingResponse])
async def get_sensor_readings(
    sensor_id: int,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    session: AsyncSession = Depends(db_manager.get_session),
):
    """
    Get historical readings for a sensor from InfluxDB
    """
    stmt = select(Sensor).where(Sensor.id == sensor_id)
    result = await session.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Sensor not found")

    return SensorService.get_sensor_readings(sensor_id, start_time, end_time)


@router.get("/{sensor_id}/readings/latest", response_model=SensorReadingResponse)
async def get_latest_sensor_reading(
    sensor_id: int,
    session: AsyncSession = Depends(db_manager.get_session),
):
    """
    Get the most recent reading for a sensor from InfluxDB
    """
    stmt = select(Sensor).where(Sensor.id == sensor_id)
    result = await session.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Sensor not found")

    reading = SensorService.get_latest_reading(sensor_id)
    if not reading:
        raise HTTPException(status_code=404, detail="No readings found for sensor")
    return reading

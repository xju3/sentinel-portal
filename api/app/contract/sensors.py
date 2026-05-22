"""
Sensor API contracts
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


# ==========================================
# SensorType
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


# ==========================================
# SensorBatch
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


# ==========================================
# Sensor
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


# ==========================================
# SensorThreshold
# ==========================================
class SensorThresholdCreate(BaseModel):
    code: str
    metric: int
    rt_max_delta: float
    st_max_slope: float
    st_max_amplitude: float
    mt_max_slope: float
    mt_max_amplitude: float
    baseline: float


class SensorThresholdUpdate(BaseModel):
    code: Optional[str] = None
    metric: Optional[int] = None
    rt_max_delta: Optional[float] = None
    st_max_slope: Optional[float] = None
    st_max_amplitude: Optional[float] = None
    mt_max_slope: Optional[float] = None
    mt_max_amplitude: Optional[float] = None
    baseline: Optional[float] = None


class SensorThresholdResponse(BaseModel):
    id: UUID
    code: str
    metric: int
    rt_max_delta: float
    st_max_slope: float
    st_max_amplitude: float
    mt_max_slope: float
    mt_max_amplitude: float
    baseline: float
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)

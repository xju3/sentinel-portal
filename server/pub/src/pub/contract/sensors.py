"""
Sensor API contracts
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    sim_id: Optional[UUID] = None


class SensorUpdate(BaseModel):
    sn: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None
    sim_id: Optional[UUID] = None


class SensorSimCardResponse(BaseModel):
    id: UUID
    number: str
    ccid: str
    carrier: str
    data_plan: str
    activated_at: Optional[datetime] = None
    expires_at: datetime
    status: int

    model_config = ConfigDict(from_attributes=True)


class SensorResponse(BaseModel):
    id: UUID
    sn: str
    description: Optional[str] = None
    active: bool
    sim_id: Optional[UUID] = None
    sim_card: Optional[SensorSimCardResponse] = None
    active_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PagedSensorResponse(BaseModel):
    items: List[SensorResponse]
    total: int


# ==========================================
# SensorTask
# ==========================================
class SensorTaskCreate(BaseModel):
    sensor_id: UUID
    name: str = Field(min_length=1, max_length=255)
    action: int
    val: int = Field(ge=1, le=32767)
    remark: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must be non-empty")
        return value

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: int) -> int:
        if 1 <= value <= 9 or 11 <= value <= 99 or 1000 <= value <= 9999:
            return value
        raise ValueError("action must be 1..9, 11..99, or 1000..9999")


class SensorTaskResponse(BaseModel):
    id: UUID
    name: str
    sn: str
    action: int
    val: int
    remark: Optional[str] = None
    status: int
    create_time: datetime
    dispatched_at: Optional[datetime] = None
    complete_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PagedSensorTaskResponse(BaseModel):
    items: List[SensorTaskResponse]
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


# ==========================================
# SensorConfig
# ==========================================
class SensorConfigIso(BaseModel):
    standard: int = 0
    category: int = 0
    foundation: int = 0


class SensorConfigWifi(BaseModel):
    ssid: Optional[str] = None
    password: Optional[str] = Field(None, serialization_alias="pass")

    model_config = ConfigDict(populate_by_name=True)


class SensorConfigResponse(BaseModel):
    iso: SensorConfigIso
    rpm: int = 0
    battery: int = 0
    host: str = ""
    patrol: int = 60
    diagnosis: int = 1440
    report: int = 1
    network: int = 1
    wifi: SensorConfigWifi
    configured: bool = False

"""
Device API contracts
"""

from datetime import date
from typing import List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ==========================================
# IsoStandard
# ==========================================
class IsoStandardCreate(BaseModel):
    code: str
    name: str
    category: str
    foundation: str
    description: Optional[str] = None


class IsoStandardUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    foundation: Optional[str] = None
    description: Optional[str] = None


class IsoStandardResponse(BaseModel):
    id: UUID
    code: str
    name: str
    category: str
    foundation: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# DeviceCategory
# ==========================================
class DeviceCategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[UUID] = None
    health_check_freq_id: UUID
    tenant_id: Optional[UUID] = None
    iso_standard_id: Optional[UUID] = None
    vib_threshold_id: Optional[UUID] = None
    temp_threshold_id: Optional[UUID] = None


class DeviceCategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[UUID] = None
    health_check_freq_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    iso_standard_id: Optional[UUID] = None
    vib_threshold_id: Optional[UUID] = None
    temp_threshold_id: Optional[UUID] = None


class HealthCheckFreqBrief(BaseModel):
    id: UUID
    patrol: int
    diagnosis: int
    report: int
    status: bool

    model_config = ConfigDict(from_attributes=True)


class DeviceCategoryMembersUpdate(BaseModel):
    employee_ids: List[UUID]


class EmployeeBrief(BaseModel):
    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class IsoStandardBrief(BaseModel):
    id: UUID
    code: str
    version: int

    model_config = ConfigDict(from_attributes=True)


class SensorThresholdBrief(BaseModel):
    id: UUID
    code: str

    model_config = ConfigDict(from_attributes=True)


class DeviceCategoryResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    parent_id: Optional[UUID] = None
    health_check_freq_id: UUID
    tenant_id: Optional[UUID] = None
    iso_standard_id: Optional[UUID] = None
    vib_threshold_id: Optional[UUID] = None
    temp_threshold_id: Optional[UUID] = None
    health_check_freq: Optional[HealthCheckFreqBrief] = None
    iso_standard: Optional[IsoStandardBrief] = None
    vib_threshold: Optional[SensorThresholdBrief] = None
    temp_threshold: Optional[SensorThresholdBrief] = None
    employees: Optional[List[EmployeeBrief]] = None

    model_config = ConfigDict(from_attributes=True)


class PagedCountResponse(BaseModel):
    total: int


# ==========================================
# DeviceSpec
# ==========================================
class DeviceSpecCreate(BaseModel):
    name: str
    model: str
    description: Optional[str] = None
    brand: str
    voltage: Optional[float] = 0.0
    rpm: Optional[int] = 0
    supplier_id: UUID
    device_category_id: UUID


class DeviceSpecUpdate(BaseModel):
    name: Optional[str] = None
    model: Optional[str] = None
    description: Optional[str] = None
    brand: Optional[str] = None
    voltage: Optional[float] = None
    rpm: Optional[int] = None
    supplier_id: Optional[UUID] = None
    device_category_id: Optional[UUID] = None


class SupplierBrief(BaseModel):
    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class DeviceCategoryBrief(BaseModel):
    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class DeviceSpecResponse(BaseModel):
    id: UUID
    name: str
    model: str
    description: Optional[str] = None
    brand: str
    voltage: float
    rpm: int
    supplier_id: UUID
    device_category_id: UUID
    supplier: Optional[SupplierBrief] = None
    device_category: Optional[DeviceCategoryBrief] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# BearingModel / DeviceSpecBearing
# ==========================================
BearingType = Literal[
    "DEEP_GROOVE_BALL",
    "ANGULAR_CONTACT_BALL",
    "SELF_ALIGNING_BALL",
    "CYLINDRICAL_ROLLER",
    "TAPERED_ROLLER",
    "SPHERICAL_ROLLER",
    "NEEDLE_ROLLER",
    "THRUST_BALL",
    "THRUST_ROLLER",
    "OTHER",
]


class BearingModelCreate(BaseModel):
    brand: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=64)
    bearing_type: Optional[BearingType] = None
    rolling_element_count: int = Field(ge=3, le=1000)
    rolling_element_diameter_mm: float = Field(gt=0, allow_inf_nan=False)
    pitch_diameter_mm: float = Field(gt=0, allow_inf_nan=False)
    contact_angle_deg: float = Field(
        default=0.0,
        ge=0,
        lt=90,
        allow_inf_nan=False,
    )
    description: Optional[str] = Field(default=None, max_length=255)
    active: bool = True

    @field_validator("brand", "model", "description")
    @classmethod
    def strip_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_geometry(self):
        if not self.brand or not self.model:
            raise ValueError("brand and model cannot be blank")
        if self.rolling_element_diameter_mm >= self.pitch_diameter_mm:
            raise ValueError(
                "rolling_element_diameter_mm must be less than pitch_diameter_mm"
            )
        return self


class BearingModelUpdate(BaseModel):
    brand: Optional[str] = Field(default=None, min_length=1, max_length=64)
    model: Optional[str] = Field(default=None, min_length=1, max_length=64)
    bearing_type: Optional[BearingType] = None
    rolling_element_count: Optional[int] = Field(default=None, ge=3, le=1000)
    rolling_element_diameter_mm: Optional[float] = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
    )
    pitch_diameter_mm: Optional[float] = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
    )
    contact_angle_deg: Optional[float] = Field(
        default=None,
        ge=0,
        lt=90,
        allow_inf_nan=False,
    )
    description: Optional[str] = Field(default=None, max_length=255)
    active: Optional[bool] = None

    @field_validator("brand", "model", "description")
    @classmethod
    def strip_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class BearingModelResponse(BearingModelCreate):
    id: UUID
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)


class DeviceSpecBearingInput(BaseModel):
    bearing_id: UUID
    location_id: UUID
    shaft_speed_ratio: float = Field(
        default=1.0,
        gt=0,
        le=1000,
        allow_inf_nan=False,
    )
    enabled: bool = True


class DeviceSpecBearingReplace(BaseModel):
    bindings: List[DeviceSpecBearingInput]

    @model_validator(mode="after")
    def validate_unique_locations(self):
        locations = [binding.location_id for binding in self.bindings]
        if len(locations) != len(set(locations)):
            raise ValueError("bearing locations must be unique within a device spec")
        return self


class BearingLocationResponse(BaseModel):
    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class DeviceSpecBearingResponse(DeviceSpecBearingInput):
    id: UUID
    device_spec_id: UUID
    bearing: BearingModelResponse
    location: BearingLocationResponse

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# DeviceInst
# ==========================================
class DeviceInstCreate(BaseModel):
    name: str
    device_spec_id: UUID
    code: str
    purchase_date: Optional[date] = None
    life_span: Optional[int] = 0
    desc: Optional[str] = None
    status: Optional[int] = 1
    active: Optional[int] = 1
    available: Optional[int] = 1


class DeviceInstUpdate(BaseModel):
    name: Optional[str] = None
    device_spec_id: Optional[UUID] = None
    code: Optional[str] = None
    purchase_date: Optional[date] = None
    life_span: Optional[int] = None
    desc: Optional[str] = None
    status: Optional[int] = None
    active: Optional[int] = None
    available: Optional[int] = None


class DeviceSpecBrief(BaseModel):
    id: UUID
    name: str
    model: str
    brand: str

    model_config = ConfigDict(from_attributes=True)


class DeviceInstResponse(BaseModel):
    id: UUID
    name: str
    device_spec_id: UUID
    code: str
    purchase_date: Optional[date] = None
    life_span: int
    desc: Optional[str] = None
    status: int
    active: int
    available: int
    device_spec: Optional[DeviceSpecBrief] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Process
# ==========================================
class ProcessCreate(BaseModel):
    tenant_id: Optional[UUID] = None
    code: str
    name: str
    status: Optional[int] = 1


class ProcessUpdate(BaseModel):
    tenant_id: Optional[UUID] = None
    code: Optional[str] = None
    name: Optional[str] = None
    status: Optional[int] = None


class ProcessResponse(BaseModel):
    id: UUID
    tenant_id: Optional[UUID] = None
    code: str
    name: str
    status: int

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# ProcessItem
# ==========================================
class ProcessItemCreate(BaseModel):
    process_id: UUID
    device_spec_id: UUID
    qty: Optional[int] = 1


class ProcessItemUpdate(BaseModel):
    process_id: Optional[UUID] = None
    device_spec_id: Optional[UUID] = None
    qty: Optional[int] = None


class ProcessItemResponse(BaseModel):
    id: UUID
    process_id: UUID
    device_spec_id: UUID
    qty: int

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# ProcessDevice
# ==========================================
class ProcessDeviceCreate(BaseModel):
    code: str
    process_id: UUID
    sn: str
    area_id: Optional[UUID] = None
    status: Optional[int] = 1


class ProcessDeviceUpdate(BaseModel):
    code: Optional[str] = None
    process_id: Optional[UUID] = None
    sn: Optional[str] = None
    area_id: Optional[UUID] = None
    status: Optional[int] = None


class ProcessBrief(BaseModel):
    id: UUID
    name: str
    code: str

class AreaBrief(BaseModel):
    id: UUID
    name: str

class ProcessDeviceResponse(BaseModel):
    id: UUID
    code: str
    process_id: UUID
    sn: str
    area_id: Optional[UUID] = None
    status: int
    employees: Optional[List[EmployeeBrief]] = None
    process: Optional[ProcessBrief] = None
    area: Optional[AreaBrief] = None

    model_config = ConfigDict(from_attributes=True)



# ==========================================
# ProcessDeviceItem
# ==========================================
class ProcessDeviceItemCreate(BaseModel):
    code: str
    desc: str
    device_inst_id: UUID
    process_device_id: UUID


class ProcessDeviceItemUpdate(BaseModel):
    code: Optional[str] = None
    desc: Optional[str] = None
    device_inst_id: Optional[UUID] = None
    process_device_id: Optional[UUID] = None


class ProcessDeviceItemResponse(BaseModel):
    id: UUID
    code: str
    desc: str
    device_inst_id: UUID
    process_device_id: UUID

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# SensorMonitoring
# ==========================================
class SensorMonitoringCreate(BaseModel):
    device_inst_id: UUID
    location_id: Optional[UUID] = None
    sensor_id: Optional[UUID] = None
    direction: Optional[str] = None
    status: Optional[int] = 1


class SensorMonitoringUpdate(BaseModel):
    device_inst_id: Optional[UUID] = None
    location_id: Optional[UUID] = None
    sensor_id: Optional[UUID] = None
    direction: Optional[str] = None
    status: Optional[int] = None


class SensorMonitoringResponse(BaseModel):
    id: UUID
    device_inst_id: UUID
    location_id: Optional[UUID] = None
    sensor_id: Optional[UUID] = None
    direction: Optional[str] = None
    anomaly: int = 0
    ts: Optional[int] = None
    status: int

    model_config = ConfigDict(from_attributes=True)


class SensorMonitoringDeviceInstOption(BaseModel):
    id: UUID
    name: str
    code: str
    device_spec_id: UUID

    model_config = ConfigDict(from_attributes=True)


class PagedDeviceInstResponse(BaseModel):
    items: List[SensorMonitoringDeviceInstOption]
    total: int

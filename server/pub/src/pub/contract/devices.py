"""
Device API contracts
"""

from datetime import date, datetime
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
    color: Optional[str] = None
    parent_id: Optional[UUID] = None
    health_check_freq_id: UUID
    tenant_id: Optional[UUID] = None
    iso_standard_id: Optional[UUID] = None
    vib_threshold_id: Optional[UUID] = None
    temp_threshold_id: Optional[UUID] = None


class DeviceCategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
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
    color: Optional[str] = None
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
# DeviceOperationSchedule / DeviceOperationScheduleItem
# ==========================================
OperationModeType = Literal[1, 2, 3]


class DeviceOperationScheduleItemInput(BaseModel):
    cron_expr: str = Field(min_length=1, max_length=64)
    duration_minutes: int = Field(gt=0, le=10080)
    remark: Optional[str] = Field(default=None, max_length=128)
    seq: int = Field(default=0, ge=0)

    @field_validator("cron_expr")
    @classmethod
    def validate_cron_expr(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        parts = normalized.split(" ")
        if len(parts) != 5:
            raise ValueError("cron_expr must be a standard 5-field cron expression")
        return normalized

    @field_validator("remark")
    @classmethod
    def strip_remark(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class DeviceOperationScheduleItemResponse(DeviceOperationScheduleItemInput):
    id: UUID
    schedule_id: UUID

    model_config = ConfigDict(from_attributes=True)


class DeviceOperationScheduleItemsReplace(BaseModel):
    items: List[DeviceOperationScheduleItemInput]


class DeviceOperationScheduleCreate(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=255)
    status: int = Field(default=1)

    @field_validator("code", "name", "description")
    @classmethod
    def strip_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_required_fields(self):
        if not self.code or not self.name:
            raise ValueError("code and name cannot be blank")
        if self.status not in (0, 1):
            raise ValueError("status must be 0 or 1")
        return self


class DeviceOperationScheduleUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=16)
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=255)
    status: Optional[int] = None

    @field_validator("code", "name", "description")
    @classmethod
    def strip_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_status(self):
        if self.status is not None and self.status not in (0, 1):
            raise ValueError("status must be 0 or 1")
        return self


class DeviceOperationScheduleBrief(BaseModel):
    id: UUID
    code: str
    name: str
    status: int = 1

    model_config = ConfigDict(from_attributes=True)


class DeviceOperationScheduleResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    code: str
    name: str
    description: Optional[str] = None
    status: int
    items: List[DeviceOperationScheduleItemResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# DeviceSpec
# ==========================================
class DeviceSpecCreate(BaseModel):
    name: str
    model: str
    description: Optional[str] = None
    brand: str
    voltage: Optional[float] = 0.0
    speed_mode: int = 1
    poles: Optional[int] = None
    frequency_hz: Optional[float] = None
    rpm: Optional[int] = 0
    remark: Optional[str] = None
    operation_mode: int = 1
    reference_id: Optional[UUID] = None
    supplier_id: UUID
    device_category_id: UUID

    @model_validator(mode="after")
    def validate_modes_and_rpm(self):
        if self.operation_mode not in (1, 2, 3):
            raise ValueError("operation_mode must be 1 (连续运行), 2 (事件触发), or 3 (时段运行)")
        if self.operation_mode == 3 and self.reference_id is None:
            raise ValueError("reference_id is required when operation_mode is 3 (时段运行)")
        if self.operation_mode in (1, 2):
            self.reference_id = None

        if self.speed_mode not in (1, 2):
            raise ValueError("speed_mode must be 1 (定速) or 2 (变频)")
        if self.speed_mode == 1:
            self.poles = None
            self.frequency_hz = None
            if self.rpm is None or self.rpm < 0:
                raise ValueError("定速模式下转速(rpm)必须为非负整数")
        else:
            if self.poles is not None and (self.poles < 2 or self.poles % 2 != 0):
                raise ValueError("电机极数(poles)必须为大于等于2的偶数（如2、4、6、8）")
            if self.frequency_hz is None or self.frequency_hz <= 0:
                self.frequency_hz = None
                self.rpm = -1
            else:
                if self.poles is None:
                    raise ValueError("变频模式下填写运行频率(Hz)时必须指定电机极数(poles)")
                self.rpm = int(round(120.0 * float(self.frequency_hz) / int(self.poles)))
        return self


class DeviceSpecUpdate(BaseModel):
    name: Optional[str] = None
    model: Optional[str] = None
    description: Optional[str] = None
    brand: Optional[str] = None
    voltage: Optional[float] = None
    speed_mode: Optional[int] = None
    poles: Optional[int] = None
    frequency_hz: Optional[float] = None
    rpm: Optional[int] = None
    remark: Optional[str] = None
    operation_mode: Optional[int] = None
    reference_id: Optional[UUID] = None
    supplier_id: Optional[UUID] = None
    device_category_id: Optional[UUID] = None

    @model_validator(mode="after")
    def validate_operation_mode(self):
        if self.operation_mode is not None and self.operation_mode not in (1, 2, 3):
            raise ValueError("operation_mode must be 1 (连续运行), 2 (事件触发), or 3 (时段运行)")
        if self.operation_mode in (1, 2):
            self.reference_id = None
        if self.speed_mode is not None and self.speed_mode not in (1, 2):
            raise ValueError("speed_mode must be 1 (定速) or 2 (变频)")
        return self


class SupplierBrief(BaseModel):
    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class DeviceCategoryBrief(BaseModel):
    id: UUID
    name: str
    color: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ProcessDeviceBrief(BaseModel):
    id: UUID
    code: str
    sn: str


class DeviceSpecResponse(BaseModel):
    id: UUID
    name: str
    model: str
    description: Optional[str] = None
    brand: str
    voltage: float
    speed_mode: int = 1
    poles: Optional[int] = None
    frequency_hz: Optional[float] = None
    rpm: int
    remark: Optional[str] = None
    operation_mode: int = 1
    reference_id: Optional[UUID] = None
    supplier_id: UUID
    device_category_id: UUID
    process_device_count: int = 0
    process_devices: List[ProcessDeviceBrief] = Field(default_factory=list)
    supplier: Optional[SupplierBrief] = None
    device_category: Optional[DeviceCategoryBrief] = None
    operation_schedule: Optional[DeviceOperationScheduleBrief] = None

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
        lt=255,
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
    remark: Optional[str] = None


class ProcessUpdate(BaseModel):
    tenant_id: Optional[UUID] = None
    code: Optional[str] = None
    name: Optional[str] = None
    status: Optional[int] = None
    remark: Optional[str] = None


class ProcessResponse(BaseModel):
    id: UUID
    tenant_id: Optional[UUID] = None
    code: str
    name: str
    status: int
    remark: Optional[str] = None

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
    color: str


class ProcessDeviceItemUpdate(BaseModel):
    code: Optional[str] = None
    desc: Optional[str] = None
    device_inst_id: Optional[UUID] = None
    process_device_id: Optional[UUID] = None
    color: Optional[str] = None


class ProcessDeviceItemResponse(BaseModel):
    id: UUID
    code: str
    desc: str
    device_inst_id: UUID
    process_device_id: UUID
    color: str

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# SensorMonitoring
# ==========================================
class SensorMonitoringCreate(BaseModel):
    device_inst_id: UUID
    location_id: UUID
    sensor_id: UUID
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
    bound_at: datetime
    unbound_at: Optional[datetime] = None

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

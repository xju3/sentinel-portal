"""
Device API contracts
"""

from datetime import date
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


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
# DeviceInst
# ==========================================
class DeviceInstCreate(BaseModel):
    name: str
    device_spec_id: UUID
    code: str
    purchase_date: date
    life_span: Optional[int] = 0
    desc: str
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
    purchase_date: date
    life_span: int
    desc: str
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

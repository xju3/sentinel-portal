"""
Customer API contracts
"""

from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


# ==========================================
# Tenant
# ==========================================
class TenantCreate(BaseModel):
    code: str
    name: str
    host: str
    active: Optional[bool] = True


class TenantUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    host: Optional[str] = None
    active: Optional[bool] = None


class TenantResponse(BaseModel):
    id: UUID
    code: str
    name: str
    host: str
    active: bool

    model_config = ConfigDict(from_attributes=True)


class CurrentTenantUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None


# ==========================================
# TenantSensor
# ==========================================
class TenantSensorCreate(BaseModel):
    tenant_id: UUID
    sensor_id: UUID
    available: Optional[bool] = True


class TenantSensorUpdate(BaseModel):
    available: Optional[bool] = None


class TenantSensorResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    sensor_id: UUID
    available: bool

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Supplier
# ==========================================
class SupplierCreate(BaseModel):
    name: str
    brand: str
    contact_info: Optional[str] = None
    active: Optional[bool] = True
    tenant_id: Optional[UUID] = None


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    contact_info: Optional[str] = None
    active: Optional[bool] = None


class SupplierResponse(BaseModel):
    id: UUID
    name: str
    brand: str
    contact_info: Optional[str] = None
    active: bool
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)


class PagedCountResponse(BaseModel):
    total: int


# ==========================================
# Account
# ==========================================
class AccountCreate(BaseModel):
    username: str
    password: str
    flag: Optional[int] = 2
    active: Optional[bool] = True
    contact_id: Optional[UUID] = None
    tenant_id: UUID


class AccountUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    flag: Optional[int] = None
    active: Optional[bool] = None
    contact_id: Optional[UUID] = None


class AccountResponse(BaseModel):
    id: UUID
    username: str
    flag: int
    active: bool
    admin: Optional[bool] = False
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)


class TenantAccountCreate(BaseModel):
    contact_name: str
    username: str
    password: str
    flag: Optional[int] = 2
    active: Optional[bool] = True


class AdminAccountCreate(BaseModel):
    contact_name: str
    username: str
    password: str


# ==========================================
# Area
# ==========================================
class AreaCreate(BaseModel):
    name: str
    description: Optional[str] = None
    ssid: Optional[str] = None
    passwd: Optional[str] = None
    parent_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None


class AreaUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    ssid: Optional[str] = None
    passwd: Optional[str] = None
    parent_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None


class AreaResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    ssid: Optional[str] = None
    passwd: Optional[str] = None
    parent_id: Optional[UUID] = None
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Location
# ==========================================
class LocationCreate(BaseModel):
    name: str
    description: Optional[str] = None
    status: Optional[int] = 1
    tenant_id: Optional[UUID] = None


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[int] = None
    tenant_id: Optional[UUID] = None


class LocationResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    status: int
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)


class PagedLocationResponse(BaseModel):
    items: List[LocationResponse]
    total: int


# ==========================================
# HealthCheckFreq
# ==========================================
class HealthCheckFreqCreate(BaseModel):
    patrol: Optional[int] = 60
    diagnosis: Optional[int] = 1440
    report: Optional[int] = 1
    status: Optional[bool] = True
    tenant_id: Optional[UUID] = None


class HealthCheckFreqUpdate(BaseModel):
    patrol: Optional[int] = None
    diagnosis: Optional[int] = None
    report: Optional[int] = None
    status: Optional[bool] = None
    tenant_id: Optional[UUID] = None


class HealthCheckFreqResponse(BaseModel):
    id: UUID
    patrol: int
    diagnosis: int
    report: int
    status: bool
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)

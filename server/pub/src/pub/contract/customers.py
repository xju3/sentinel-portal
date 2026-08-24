"""
Customer API contracts
"""

from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict


# ==========================================
# Region
# ==========================================
class RegionResponse(BaseModel):
    id: str
    name: str
    province: Optional[str] = None
    prefecture: Optional[str] = None
    county: Optional[str] = None
    level: Optional[int] = 1
    available: Optional[bool] = True
    abbreviation: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Tenant
# ==========================================
class TenantCreate(BaseModel):
    code: str
    name: str
    mqtt_server: str = "mqtt.api-server.icu"
    api_server: str = "api.api-server.icu"
    region_id: str
    active: Optional[bool] = True
    status: Optional[int] = 1
    industry: Optional[int] = None
    email: Optional[str] = None
    remark: Optional[str] = None


class TenantUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    mqtt_server: Optional[str] = None
    api_server: Optional[str] = None
    region_id: Optional[str] = None
    active: Optional[bool] = None
    status: Optional[int] = None
    industry: Optional[int] = None
    email: Optional[str] = None
    remark: Optional[str] = None


class TenantResponse(BaseModel):
    id: UUID
    code: str
    name: str
    mqtt_server: str
    api_server: str
    region_id: Optional[str] = None
    active: bool
    web_site: Optional[str] = None
    desc: Optional[str] = None
    create_at: datetime
    src: Optional[int] = None
    status: Optional[int] = None
    industry: Optional[int] = None
    email: Optional[str] = None
    email_status: Optional[int] = None
    remark: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CurrentTenantUpdate(BaseModel):
    name: Optional[str] = None
    mqtt_server: Optional[str] = None
    api_server: Optional[str] = None


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
    admin: bool
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    tenant_id: UUID
    wx_user_id: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None
    employee_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


class TenantAccountCreate(BaseModel):
    contact_name: str
    username: str
    password: str
    flag: Optional[int] = 2
    active: Optional[bool] = True
    employee_id: Optional[UUID] = None


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
    network: Optional[int] = 1  # 1: 4G, 2: Wi-Fi
    ssid: Optional[str] = None
    passwd: Optional[str] = None
    parent_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None


class AreaUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    network: Optional[int] = None  # 1: 4G, 2: Wi-Fi
    ssid: Optional[str] = None
    passwd: Optional[str] = None
    parent_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None


class AreaResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    network: int
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
    is_bearing_point: bool = False
    status: Optional[int] = 1
    tenant_id: Optional[UUID] = None


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_bearing_point: Optional[bool] = None
    status: Optional[int] = None
    tenant_id: Optional[UUID] = None


class LocationResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    is_bearing_point: bool
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


# ==========================================
# IsoStandard
# ==========================================
class IsoStandardCreate(BaseModel):
    code: str
    version: int  # 1: ISO-10816, 2: ISO-20816
    category: int  # version-dependent
    foundation: int  # 1: 刚性基础, 2: 柔性基础
    description: Optional[str] = None
    tenant_id: Optional[UUID] = None


class IsoStandardUpdate(BaseModel):
    code: Optional[str] = None
    version: Optional[int] = None
    category: Optional[int] = None
    foundation: Optional[int] = None
    description: Optional[str] = None
    tenant_id: Optional[UUID] = None


class IsoStandardResponse(BaseModel):
    id: UUID
    code: str
    version: int
    category: int
    foundation: int
    description: Optional[str] = None
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)

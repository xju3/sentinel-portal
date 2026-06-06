from pydantic import BaseModel, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime

class SensorFirmwareCreate(BaseModel):
    version: str
    description: Optional[str] = None
    file_url: str
    sensor_type_id: UUID
    tenant_id: Optional[UUID] = None

class SensorFirmwareUpdate(BaseModel):
    version: Optional[str] = None
    description: Optional[str] = None
    file_url: Optional[str] = None
    sensor_type_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None

class SensorFirmwareResponse(BaseModel):
    id: UUID
    version: str
    description: Optional[str] = None
    release_date: Optional[datetime] = None
    file_url: str
    sensor_type_id: UUID
    tenant_id: Optional[UUID] = None
    status: int

    model_config = ConfigDict(from_attributes=True)


class PresignedUploadRequest(BaseModel):
    version: str
    filename: str


class PresignedUploadResponse(BaseModel):
    presigned_url: str
    file_url: str
    object_name: str

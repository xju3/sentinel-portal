"""
Admin API contracts
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


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

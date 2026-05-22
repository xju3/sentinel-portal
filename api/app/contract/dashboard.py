"""
Dashboard API contracts
"""

from typing import List, Optional
from pydantic import BaseModel


class AnomalyResponse(BaseModel):
    id: str
    device_code: str
    device_sn: str
    anomaly: int
    ts: int


class CategoryCountResponse(BaseModel):
    name: str
    value: int


class CategoryTreeNodeResponse(BaseModel):
    """Recursive tree node for device category device distribution"""
    name: str
    total: int
    anomaly: int
    children: Optional[List["CategoryTreeNodeResponse"]] = None


class DashboardOverviewResponse(BaseModel):
    totalDevices: int
    runningDevices: int
    faultyDevices: int
    newDevicesToday: int
    recentAnomalies: List[AnomalyResponse]
    devicesByCategory: List[CategoryCountResponse] = []
    devicesByCategoryTree: List[CategoryTreeNodeResponse] = []


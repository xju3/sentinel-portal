"""
Dashboard API contracts
"""

from typing import List
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


class DashboardOverviewResponse(BaseModel):
    totalDevices: int
    runningDevices: int
    faultyDevices: int
    newDevicesToday: int
    recentAnomalies: List[AnomalyResponse]
    devicesByCategory: List[CategoryCountResponse] = []

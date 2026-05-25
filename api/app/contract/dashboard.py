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


class CalendarDayResponse(BaseModel):
    """Single day's fault count for calendar heatmap"""
    date: str  # "2026-05-25"
    count: int  # Number of faulty devices on that day
    level: int  # 0-4 color level


class CalendarMonthResponse(BaseModel):
    """Month data for calendar heatmap"""
    month: int  # 1-12
    days: List[CalendarDayResponse]


class CalendarResponse(BaseModel):
    """Calendar heatmap data response"""
    year: int
    months: List[CalendarMonthResponse]


class DashboardOverviewResponse(BaseModel):
    totalDevices: int
    runningDevices: int
    faultyDevices: int
    newDevicesToday: int
    recentAnomalies: List[AnomalyResponse]
    devicesByCategory: List[CategoryCountResponse] = []
    devicesByCategoryTree: List[CategoryTreeNodeResponse] = []
    devicesByAreaTree: List[CategoryTreeNodeResponse] = []


"""
Dashboard related endpoints
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from pydantic import BaseModel

from app.database import db_manager
from app.models.customer import Account as AccountModel
from app.utils.auth import get_current_account
from app.services.dashboard_service import DashboardService

router = APIRouter(tags=["dashboard"])

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

@router.get("/dashboard/overview", response_model=DashboardOverviewResponse)
async def get_dashboard_overview(
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    return await DashboardService.get_overview(session, tenant_id)

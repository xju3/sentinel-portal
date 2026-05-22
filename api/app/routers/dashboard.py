"""
Dashboard related endpoints
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dependencies import get_session
from app.models.customer import Account as AccountModel
from app.utils.auth import get_current_account
from app.services.dashboard_service import DashboardService
from app.contract.dashboard import DashboardOverviewResponse

router = APIRouter(tags=["dashboard"])

@router.get("/dashboard/overview", response_model=DashboardOverviewResponse)
async def get_dashboard_overview(
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    return await DashboardService.get_overview(session, tenant_id)

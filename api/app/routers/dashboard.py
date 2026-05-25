"""
Dashboard related endpoints
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.response import success
from app.services.dependencies import get_session
from app.models.customer import Account as AccountModel
from app.utils.auth import get_current_account
from app.services.dashboard_service import DashboardService
from app.contract.dashboard import CalendarResponse, DashboardOverviewResponse

router = APIRouter(tags=["dashboard"])

@router.get("/dashboard/overview")
async def get_dashboard_overview(
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = current_account.tenant_id
    return success(await DashboardService.get_overview(session, tenant_id))


@router.get("/dashboard/calendar")
async def get_dashboard_calendar(
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    """Get calendar heatmap data for the past 12 months.
    
    Returns daily fault device counts with color levels (0-4).
    Today's data is queried from DB; historical data uses Redis cache.
    Also returns the tenant's create_at date for frontend color differentiation.
    """
    tenant_id = current_account.tenant_id
    return success(await DashboardService.get_calendar_data(session, tenant_id))

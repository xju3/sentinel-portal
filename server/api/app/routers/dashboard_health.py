"""
Dashboard Health endpoints
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import cast
from uuid import UUID

from app.utils.response import success
from pub.services import get_session
from pub.models.customer import Account as AccountModel
from app.utils.auth import get_current_account
from pub.services import DashboardHealthService

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/health")
async def get_dashboard_health(
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    return success(await DashboardHealthService.get_health_dashboard(session, tenant_id))

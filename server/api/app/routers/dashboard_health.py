"""
Dashboard Health endpoints
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Query
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
    background_tasks: BackgroundTasks,
    refresh: bool = Query(False, description="Ignore Redis snapshot and rebuild now"),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    if refresh:
        await DashboardHealthService.refresh_health_dashboard(tenant_id)
    data = await DashboardHealthService.get_health_dashboard(session, tenant_id)
    if data.get("snapshot", {}).get("stale"):
        data["snapshot"]["refreshing"] = True
        background_tasks.add_task(
            DashboardHealthService.refresh_health_dashboard,
            tenant_id,
        )
    return success(data)

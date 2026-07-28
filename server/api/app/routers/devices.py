"""
Device related endpoints
"""

import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import cast
from uuid import UUID

from app.utils.auth import get_current_account
from app.utils.response import success
from pub.models.customer import Account
from pub.services import get_session
from pub.services import DashboardHealthService, DeviceHealthArchiveService
from pub.services.device.device_inst_service import DeviceInstService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("/{device_id}/health-archive")
async def get_device_health_archive(
    device_id: UUID,
    start_at: datetime | None = Query(
        None,
        description="UTC start time; defaults to seven days before end_at",
    ),
    end_at: datetime | None = Query(
        None,
        description="UTC end time; defaults to now",
    ),
    interval_hours: int = Query(
        1,
        ge=1,
        le=168,
        description="Timeline bucket size in hours; minimum is one hour",
    ),
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    if not await DeviceInstService.is_tenant_device_inst(
        session,
        tenant_id,
        device_id,
    ):
        raise HTTPException(status_code=404, detail="Device not found")

    try:
        normalized_start, normalized_end = DeviceHealthArchiveService.normalize_range(
            start_at,
            end_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    device = await DeviceInstService.get_by_id(session, device_id)
    timeline = await DeviceHealthArchiveService.get_timeline(
        session=session,
        tenant_id=tenant_id,
        device_id=device_id,
        start_at=normalized_start,
        end_at=normalized_end,
        interval_hours=interval_hours,
    )
    timeline["device"] = {
        "id": str(device.id),
        "name": device.name,
        "code": device.code,
    }
    return success(timeline)


@router.get("/faults")
async def list_fault_devices(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    """
    Get a list of all devices that are in a fault state (not normal).
    """
    tenant_id = cast(UUID, current_account.tenant_id)
    dashboard_data = await DashboardHealthService.get_health_dashboard(session, tenant_id)
    if dashboard_data.get("snapshot", {}).get("stale"):
        background_tasks.add_task(
            DashboardHealthService.refresh_health_dashboard,
            tenant_id,
        )
    return success(dashboard_data.get("faultDevices", []))

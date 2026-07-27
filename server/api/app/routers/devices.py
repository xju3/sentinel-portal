"""
Device related endpoints
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import cast
from uuid import UUID

from app.utils.auth import get_current_account
from app.utils.response import success
from pub.models.customer import Account
from pub.services import get_session
from pub.services import DashboardHealthService # Corrected import

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("/faults")
async def list_fault_devices(
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    """
    Get a list of all devices that are in a fault state (not normal).
    """
    dashboard_data = await DashboardHealthService.get_health_dashboard(session, cast(UUID, current_account.tenant_id)) # Corrected method call
    return success(dashboard_data.get("faultDevices", []))
"""
Admin management endpoints - for admin backend only, no tenant filtering
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

logger = logging.getLogger(__name__)

from app.utils.response import success
from pub.services.dependencies import get_session
from pub.services.sensor_service import SensorBatchService
from pub.models.customer import Account
from app.utils.auth import get_current_account
from app.contract.admin import SensorBatchResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/sensor-batches")
async def list_all_sensor_batches(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    """List all sensor batches across all tenants (admin only)"""
    return success(await SensorBatchService.get_all(session, skip, limit))


@router.get("/sensor-batches/{obj_id}")
async def get_sensor_batch(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    """Get a sensor batch by id (admin only, no tenant check)"""
    obj = await SensorBatchService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="SensorBatch not found")
    return success(obj)

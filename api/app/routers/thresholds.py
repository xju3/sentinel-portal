"""
Sensor threshold management endpoints
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

logger = logging.getLogger(__name__)


from app.services.dependencies import get_session
from app.services.sensor_service import SensorThresholdService
from app.models.customer import Account
from app.utils.auth import get_current_account
from app.contract.sensors import (
    SensorThresholdCreate,
    SensorThresholdUpdate,
    SensorThresholdResponse,
)

router = APIRouter(prefix="/thresholds", tags=["thresholds"])


@router.get("", response_model=List[SensorThresholdResponse])
async def list_sensor_thresholds(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    return await SensorThresholdService.get_by_tenant(session, current_account.tenant_id, skip, limit)


@router.get("/{obj_id}", response_model=SensorThresholdResponse)
async def get_sensor_threshold(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    obj = await SensorThresholdService.get_by_id_and_tenant(session, obj_id, current_account.tenant_id)
    if not obj:
        raise HTTPException(status_code=404, detail="SensorThreshold not found")
    return obj


@router.post("", response_model=SensorThresholdResponse)
async def create_sensor_threshold(
    item: SensorThresholdCreate,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    data = item.model_dump()
    data["tenant_id"] = current_account.tenant_id
    return await SensorThresholdService.create(session, data)


@router.put("/{obj_id}", response_model=SensorThresholdResponse)
async def update_sensor_threshold(
    obj_id: UUID,
    item: SensorThresholdUpdate,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    db_obj = await SensorThresholdService.get_by_id_and_tenant(session, obj_id, current_account.tenant_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorThreshold not found")

    update_data = item.model_dump(exclude_unset=True)
    return await SensorThresholdService.update(session, db_obj, update_data)


@router.delete("/{obj_id}")
async def delete_sensor_threshold(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    db_obj = await SensorThresholdService.get_by_id_and_tenant(session, obj_id, current_account.tenant_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorThreshold not found")

    await SensorThresholdService.delete(session, db_obj)
    return {"message": "SensorThreshold deleted successfully"}

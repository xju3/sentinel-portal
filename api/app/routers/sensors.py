"""
Sensor management endpoints
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import cast, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


from app.services.dependencies import get_session
from app.services.sensor_service import SensorTypeService, SensorDbService, SensorBatchService
from app.models.customer import Account
from app.models.sensor import Sensor, SensorBatch
from app.utils.auth import get_current_account
from app.utils.response import success
from app.utils.exceptions import DomainException
from app.utils.decorators import rebuild_dashboard_cache
from app.contract.sensors import (
    SensorTypeCreate,
    SensorTypeUpdate,
    SensorTypeResponse,
    SensorBatchCreate,
    SensorBatchUpdate,
    SensorBatchResponse,
    SensorCreate,
    SensorUpdate,
    SensorResponse,
    PagedSensorResponse,
)

router = APIRouter(prefix="/sensors", tags=["sensors"])


# ==========================================
# 1. SensorType
# ==========================================
@router.get("/types")
async def list_sensor_types(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    session: AsyncSession = Depends(get_session),
):
    return success(await SensorTypeService.get_all(session, skip, limit, sort_by, sort_order))


@router.get("/types/{obj_id}")
async def get_sensor_type(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    obj = await SensorTypeService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="SensorType not found")
    return success(obj)


@router.post("/types")
@rebuild_dashboard_cache()
async def create_sensor_type(
    item: SensorTypeCreate,
    session: AsyncSession = Depends(get_session),
):
    return success(await SensorTypeService.create(session, item.model_dump()))


@router.put("/types/{obj_id}")
@rebuild_dashboard_cache()
async def update_sensor_type(
    obj_id: UUID,
    item: SensorTypeUpdate,
    session: AsyncSession = Depends(get_session),
):
    db_obj = await SensorTypeService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorType not found")

    update_data = item.model_dump(exclude_unset=True)
    return success(await SensorTypeService.update(session, db_obj, update_data))


@router.delete("/types/{obj_id}")
@rebuild_dashboard_cache()
async def delete_sensor_type(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    db_obj = await SensorTypeService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorType not found")

    await SensorTypeService.delete(session, db_obj)
    return success({"message": "SensorType deleted successfully"})


# ==========================================
# 2. SensorBatch (defined before Sensor to avoid path conflict with /{obj_id})
# ==========================================
@router.get("/batches")
async def list_sensor_batches(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    stmt = select(SensorBatch).where(SensorBatch.tenant_id == current_account.tenant_id)
    if sort_by and hasattr(SensorBatch, sort_by):
        col = getattr(SensorBatch, sort_by)
        stmt = stmt.order_by(col.desc() if sort_order == "descend" else col.asc())
    else:
        stmt = stmt.order_by(SensorBatch.created_at.desc())

    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    items = (await session.execute(stmt.offset(skip).limit(limit))).scalars().all()
    return success({"items": items, "total": total})

@router.get("/batches/{obj_id}")
async def get_sensor_batch(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    obj = await SensorBatchService.get_by_id_and_tenant(session, obj_id, cast(UUID, current_account.tenant_id))
    if not obj:
        raise HTTPException(status_code=404, detail="SensorBatch not found")
    return success(obj)


@router.post("/batches")
@rebuild_dashboard_cache()
async def create_sensor_batch(
    item: SensorBatchCreate,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    data = item.model_dump()
    data["tenant_id"] = cast(UUID, current_account.tenant_id)
    return success(await SensorBatchService.create(session, data))


@router.put("/batches/{obj_id}")
@rebuild_dashboard_cache()
async def update_sensor_batch(
    obj_id: UUID,
    item: SensorBatchUpdate,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    db_obj = await SensorBatchService.get_by_id_and_tenant(session, obj_id, cast(UUID, current_account.tenant_id))
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorBatch not found")

    update_data = item.model_dump(exclude_unset=True)
    return success(await SensorBatchService.update(session, db_obj, update_data))


@router.delete("/batches/{obj_id}")
@rebuild_dashboard_cache()
async def delete_sensor_batch(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    db_obj = await SensorBatchService.get_by_id_and_tenant(session, obj_id, cast(UUID, current_account.tenant_id))
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorBatch not found")

    await SensorBatchService.delete(session, db_obj)
    return success({"message": "SensorBatch deleted successfully"})


# ==========================================
# 3. Sensor
# ==========================================
@router.get("")
async def list_sensors(
    current: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    session: AsyncSession = Depends(get_session),
):
    items, total = await SensorDbService.get_paged(session, current, pageSize, keyword, sort_by, sort_order)
    return success(PagedSensorResponse(items=items, total=total))


@router.get("/by-batch/{batch_id}")
async def list_sensors_by_batch(
    batch_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    session: AsyncSession = Depends(get_session),
    current_account: Account = Depends(get_current_account),
):
    # Verify the batch belongs to the current tenant
    batch = await SensorBatchService.get_by_id_and_tenant(session, batch_id, cast(UUID, current_account.tenant_id))
    if not batch:
        raise HTTPException(status_code=404, detail="SensorBatch not found")
    return success(await SensorDbService.get_by_batch_id(session, batch_id, skip, limit, sort_by, sort_order))


@router.get("/{obj_id}")
async def get_sensor(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    obj = await SensorDbService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return success(obj)


@router.post("")
@rebuild_dashboard_cache()
async def create_sensor(
    item: SensorCreate,
    session: AsyncSession = Depends(get_session),
):
    return success(await SensorDbService.create(session, item.model_dump()))


@router.put("/{obj_id}")
@rebuild_dashboard_cache()
async def update_sensor(
    obj_id: UUID,
    item: SensorUpdate,
    session: AsyncSession = Depends(get_session),
):
    db_obj = await SensorDbService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Sensor not found")

    update_data = item.model_dump(exclude_unset=True)
    return success(await SensorDbService.update(session, db_obj, update_data))


@router.delete("/{obj_id}")
@rebuild_dashboard_cache()
async def delete_sensor(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    db_obj = await SensorDbService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Sensor not found")

    await SensorDbService.delete(session, db_obj)
    return success({"message": "Sensor deleted successfully"})

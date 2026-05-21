"""
Device related management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import date
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from uuid import UUID

from app.database import db_manager
from app.models.customer import Account as AccountModel, Location, TenantSensor
from app.models.device import DeviceCategory, DeviceInst, DeviceSpec
from app.models.sensor import SensorMonitoring
from app.services.device_service import (
    IsoStandardService,
    DeviceCategoryService,
    DeviceSpecService,
    DeviceInstService,
    ProcessService,
    ProcessItemService,
    ProcessDeviceService,
    ProcessDeviceItemService,
    SensorMonitoringService,
)
from app.utils.auth import get_current_account

router = APIRouter(tags=["devices"])


async def _is_tenant_device_inst(
    session: AsyncSession,
    tenant_id: UUID,
    device_inst_id: UUID,
) -> bool:
    stmt = (
        select(DeviceInst.id)
        .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
        .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
        .where(
            DeviceInst.id == device_inst_id,
            DeviceCategory.tenant_id == tenant_id,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _validate_sensor_monitoring_refs(
    session: AsyncSession,
    tenant_id: UUID,
    data: dict,
) -> None:
    device_inst_id = data.get("device_inst_id")
    if device_inst_id is not None:
        ok = await _is_tenant_device_inst(session, tenant_id, device_inst_id)
        if not ok:
            raise HTTPException(status_code=400, detail="device_inst_id is not owned by current tenant")

    location_id = data.get("location_id")
    if location_id is not None:
        stmt_loc = select(Location.id).where(
            Location.id == location_id,
            Location.tenant_id == tenant_id,
        ).limit(1)
        loc_result = await session.execute(stmt_loc)
        if loc_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail="location_id is not owned by current tenant")

    # sensor_id 校验已移除，传感器选择器已确保只显示可用传感器


# ==========================================
# 1. IsoStandard
# ==========================================
class IsoStandardCreate(BaseModel):
    code: str
    name: str
    category: str
    foundation: str
    description: Optional[str] = None


class IsoStandardUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    foundation: Optional[str] = None
    description: Optional[str] = None


class IsoStandardResponse(BaseModel):
    id: UUID
    code: str
    name: str
    category: str
    foundation: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


@router.get("/iso-standards", response_model=List[IsoStandardResponse])
async def list_iso_standards(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await IsoStandardService.get_all(session, skip, limit)


@router.get("/iso-standards/{obj_id}", response_model=IsoStandardResponse)
async def get_iso_standard(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    obj = await IsoStandardService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="IsoStandard not found")
    return obj


@router.post("/iso-standards", response_model=IsoStandardResponse)
async def create_iso_standard(
    item: IsoStandardCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await IsoStandardService.create(session, item.model_dump())


@router.put("/iso-standards/{obj_id}", response_model=IsoStandardResponse)
async def update_iso_standard(
    obj_id: UUID,
    item: IsoStandardUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await IsoStandardService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="IsoStandard not found")

    update_data = item.model_dump(exclude_unset=True)
    return await IsoStandardService.update(session, db_obj, update_data)


@router.delete("/iso-standards/{obj_id}")
async def delete_iso_standard(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await IsoStandardService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="IsoStandard not found")

    await IsoStandardService.delete(session, db_obj)
    return {"message": "IsoStandard deleted successfully"}


# ==========================================
# 2. DeviceCategory
# ==========================================
class DeviceCategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[UUID] = None
    health_check_freq_id: UUID
    tenant_id: Optional[UUID] = None
    iso_standard_id: Optional[UUID] = None


class DeviceCategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[UUID] = None
    health_check_freq_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    iso_standard_id: Optional[UUID] = None


class HealthCheckFreqBrief(BaseModel):
    id: UUID
    patrol: int
    diagnosis: int
    report: int
    status: bool

    model_config = ConfigDict(from_attributes=True)


class DeviceCategoryResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    parent_id: Optional[UUID] = None
    health_check_freq_id: UUID
    tenant_id: Optional[UUID] = None
    iso_standard_id: Optional[UUID] = None
    health_check_freq: Optional[HealthCheckFreqBrief] = None

    model_config = ConfigDict(from_attributes=True)


class PagedCountResponse(BaseModel):
    total: int


def _serialize_device_category(
    item,
    freq_obj=None,
) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "parent_id": item.parent_id,
        "health_check_freq_id": item.health_check_freq_id,
        "tenant_id": item.tenant_id,
        "iso_standard_id": item.iso_standard_id,
        "health_check_freq": (
            {
                "id": freq_obj.id,
                "patrol": freq_obj.patrol,
                "diagnosis": freq_obj.diagnosis,
                "report": freq_obj.report,
                "status": freq_obj.status,
            }
            if freq_obj is not None
            else None
        ),
    }


async def _validate_device_category_parent(
    session: AsyncSession,
    tenant_id: UUID,
    parent_id: Optional[UUID],
    current_id: Optional[UUID] = None,
) -> None:
    if parent_id is None:
        return

    if current_id is not None and parent_id == current_id:
        raise HTTPException(status_code=400, detail="parent_id cannot be self")

    cursor = parent_id
    visited = set()
    while cursor is not None:
        if cursor in visited:
            raise HTTPException(status_code=400, detail="Cycle detected in category hierarchy")
        visited.add(cursor)

        parent = await DeviceCategoryService.get_by_id(session, tenant_id, cursor)
        if not parent:
            raise HTTPException(status_code=400, detail="Parent category not found")

        if current_id is not None and parent.id == current_id:
            raise HTTPException(status_code=400, detail="Cycle detected in category hierarchy")

        cursor = parent.parent_id


@router.get("/device-categories", response_model=List[DeviceCategoryResponse])
async def list_device_categories(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    rows = await DeviceCategoryService.get_all(session, tenant_id, skip, limit, keyword)
    freq_map = await DeviceCategoryService.get_health_check_freq_map(
        session,
        tenant_id,
        [row.health_check_freq_id for row in rows],
    )
    return [
        _serialize_device_category(row, freq_map.get(row.health_check_freq_id))
        for row in rows
    ]


@router.get("/device-categories/count", response_model=PagedCountResponse)
async def count_device_categories(
    keyword: Optional[str] = Query(None),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    total = await DeviceCategoryService.count_all(session, tenant_id, keyword)
    return {"total": total}


@router.get("/device-categories/{obj_id}", response_model=DeviceCategoryResponse)
async def get_device_category(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    obj = await DeviceCategoryService.get_by_id(session, tenant_id, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="DeviceCategory not found")
    freq_map = await DeviceCategoryService.get_health_check_freq_map(
        session,
        tenant_id,
        [obj.health_check_freq_id],
    )
    return _serialize_device_category(obj, freq_map.get(obj.health_check_freq_id))


@router.post("/device-categories", response_model=DeviceCategoryResponse)
async def create_device_category(
    item: DeviceCategoryCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    payload = item.model_dump(exclude_unset=True)
    if "tenant_id" in payload and payload["tenant_id"] is not None and payload["tenant_id"] != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id mismatch")
    payload["tenant_id"] = tenant_id
    await _validate_device_category_parent(session, tenant_id, payload.get("parent_id"))
    created = await DeviceCategoryService.create(session, payload)
    freq_map = await DeviceCategoryService.get_health_check_freq_map(
        session,
        tenant_id,
        [created.health_check_freq_id],
    )
    return _serialize_device_category(created, freq_map.get(created.health_check_freq_id))


@router.put("/device-categories/{obj_id}", response_model=DeviceCategoryResponse)
async def update_device_category(
    obj_id: UUID,
    item: DeviceCategoryUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    db_obj = await DeviceCategoryService.get_by_id(session, tenant_id, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceCategory not found")

    update_data = item.model_dump(exclude_unset=True)
    if "tenant_id" in update_data and update_data["tenant_id"] != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id cannot be changed")
    update_data.pop("tenant_id", None)
    if "parent_id" in update_data:
        await _validate_device_category_parent(session, tenant_id, update_data.get("parent_id"), obj_id)
    updated = await DeviceCategoryService.update(session, db_obj, update_data)
    freq_map = await DeviceCategoryService.get_health_check_freq_map(
        session,
        tenant_id,
        [updated.health_check_freq_id],
    )
    return _serialize_device_category(updated, freq_map.get(updated.health_check_freq_id))


@router.delete("/device-categories/{obj_id}")
async def delete_device_category(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    db_obj = await DeviceCategoryService.get_by_id(session, tenant_id, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceCategory not found")

    has_children = await DeviceCategoryService.has_children(session, tenant_id, obj_id)
    if has_children:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete category with child categories",
        )

    await DeviceCategoryService.delete(session, db_obj)
    return {"message": "DeviceCategory deleted successfully"}


# ==========================================
# 3. DeviceSpec
# ==========================================
class DeviceSpecCreate(BaseModel):
    name: str
    model: str
    description: Optional[str] = None
    brand: str
    voltage: Optional[float] = 0.0
    rpm: Optional[int] = 0
    supplier_id: UUID
    device_category_id: UUID


class DeviceSpecUpdate(BaseModel):
    name: Optional[str] = None
    model: Optional[str] = None
    description: Optional[str] = None
    brand: Optional[str] = None
    voltage: Optional[float] = None
    rpm: Optional[int] = None
    supplier_id: Optional[UUID] = None
    device_category_id: Optional[UUID] = None


class DeviceSpecResponse(BaseModel):
    id: UUID
    name: str
    model: str
    description: Optional[str] = None
    brand: str
    voltage: float
    rpm: int
    supplier_id: UUID
    device_category_id: UUID

    model_config = ConfigDict(from_attributes=True)


@router.get("/device-specs", response_model=List[DeviceSpecResponse])
async def list_device_specs(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await DeviceSpecService.get_all(session, skip, limit)


@router.get("/device-specs/{obj_id}", response_model=DeviceSpecResponse)
async def get_device_spec(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    obj = await DeviceSpecService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="DeviceSpec not found")
    return obj


@router.post("/device-specs", response_model=DeviceSpecResponse)
async def create_device_spec(
    item: DeviceSpecCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await DeviceSpecService.create(session, item.model_dump())


@router.put("/device-specs/{obj_id}", response_model=DeviceSpecResponse)
async def update_device_spec(
    obj_id: UUID,
    item: DeviceSpecUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await DeviceSpecService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceSpec not found")

    update_data = item.model_dump(exclude_unset=True)
    return await DeviceSpecService.update(session, db_obj, update_data)


@router.delete("/device-specs/{obj_id}")
async def delete_device_spec(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await DeviceSpecService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceSpec not found")

    await DeviceSpecService.delete(session, db_obj)
    return {"message": "DeviceSpec deleted successfully"}


# ==========================================
# 4. DeviceInst
# ==========================================
class DeviceInstCreate(BaseModel):
    code: str
    device_spec_id: UUID
    sn: str
    purchase_date: date
    life_span: Optional[int] = 0
    desc: str
    status: Optional[int] = 1


class DeviceInstUpdate(BaseModel):
    code: Optional[str] = None
    device_spec_id: Optional[UUID] = None
    sn: Optional[str] = None
    purchase_date: Optional[date] = None
    life_span: Optional[int] = None
    desc: Optional[str] = None
    status: Optional[int] = None


class DeviceInstResponse(BaseModel):
    id: UUID
    code: str
    device_spec_id: UUID
    sn: str
    purchase_date: date
    life_span: int
    desc: str
    status: int

    model_config = ConfigDict(from_attributes=True)


@router.get("/device-insts", response_model=List[DeviceInstResponse])
async def list_device_insts(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await DeviceInstService.get_all(session, skip, limit)


@router.get("/device-insts/{obj_id}", response_model=DeviceInstResponse)
async def get_device_inst(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    obj = await DeviceInstService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="DeviceInst not found")
    return obj


@router.post("/device-insts", response_model=DeviceInstResponse)
async def create_device_inst(
    item: DeviceInstCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await DeviceInstService.create(session, item.model_dump())


@router.put("/device-insts/{obj_id}", response_model=DeviceInstResponse)
async def update_device_inst(
    obj_id: UUID,
    item: DeviceInstUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await DeviceInstService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceInst not found")

    update_data = item.model_dump(exclude_unset=True)
    return await DeviceInstService.update(session, db_obj, update_data)


@router.delete("/device-insts/{obj_id}")
async def delete_device_inst(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await DeviceInstService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceInst not found")

    await DeviceInstService.delete(session, db_obj)
    return {"message": "DeviceInst deleted successfully"}


# ==========================================
# 5. Process
# ==========================================
class ProcessCreate(BaseModel):
    tenant_id: Optional[UUID] = None
    code: str
    name: str
    status: Optional[int] = 1


class ProcessUpdate(BaseModel):
    tenant_id: Optional[UUID] = None
    code: Optional[str] = None
    name: Optional[str] = None
    status: Optional[int] = None


class ProcessResponse(BaseModel):
    id: UUID
    tenant_id: Optional[UUID] = None
    code: str
    name: str
    status: int

    model_config = ConfigDict(from_attributes=True)


@router.get("/processes", response_model=List[ProcessResponse])
async def list_processes(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await ProcessService.get_all(session, skip, limit)


@router.get("/processes/{obj_id}", response_model=ProcessResponse)
async def get_process(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    obj = await ProcessService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Process not found")
    return obj


@router.post("/processes", response_model=ProcessResponse)
async def create_process(
    item: ProcessCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await ProcessService.create(session, item.model_dump())


@router.put("/processes/{obj_id}", response_model=ProcessResponse)
async def update_process(
    obj_id: UUID,
    item: ProcessUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await ProcessService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Process not found")

    update_data = item.model_dump(exclude_unset=True)
    return await ProcessService.update(session, db_obj, update_data)


@router.delete("/processes/{obj_id}")
async def delete_process(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await ProcessService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Process not found")

    await ProcessService.delete(session, db_obj)
    return {"message": "Process deleted successfully"}


# ==========================================
# 6. ProcessItem
# ==========================================
class ProcessItemCreate(BaseModel):
    process_id: UUID
    device_spec_id: UUID
    qty: Optional[int] = 1


class ProcessItemUpdate(BaseModel):
    process_id: Optional[UUID] = None
    device_spec_id: Optional[UUID] = None
    qty: Optional[int] = None


class ProcessItemResponse(BaseModel):
    id: UUID
    process_id: UUID
    device_spec_id: UUID
    qty: int

    model_config = ConfigDict(from_attributes=True)


@router.get("/process-items", response_model=List[ProcessItemResponse])
async def list_process_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await ProcessItemService.get_all(session, skip, limit)


@router.get("/process-items/{obj_id}", response_model=ProcessItemResponse)
async def get_process_item(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    obj = await ProcessItemService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="ProcessItem not found")
    return obj


@router.post("/process-items", response_model=ProcessItemResponse)
async def create_process_item(
    item: ProcessItemCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await ProcessItemService.create(session, item.model_dump())


@router.put("/process-items/{obj_id}", response_model=ProcessItemResponse)
async def update_process_item(
    obj_id: UUID,
    item: ProcessItemUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await ProcessItemService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="ProcessItem not found")

    update_data = item.model_dump(exclude_unset=True)
    return await ProcessItemService.update(session, db_obj, update_data)


@router.delete("/process-items/{obj_id}")
async def delete_process_item(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await ProcessItemService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="ProcessItem not found")

    await ProcessItemService.delete(session, db_obj)
    return {"message": "ProcessItem deleted successfully"}


# ==========================================
# 7. ProcessDevice
# ==========================================
class ProcessDeviceCreate(BaseModel):
    code: str
    process_id: UUID
    sn: str
    area_id: Optional[UUID] = None
    status: Optional[int] = 1


class ProcessDeviceUpdate(BaseModel):
    code: Optional[str] = None
    process_id: Optional[UUID] = None
    sn: Optional[str] = None
    area_id: Optional[UUID] = None
    status: Optional[int] = None


class ProcessDeviceResponse(BaseModel):
    id: UUID
    code: str
    process_id: UUID
    sn: str
    area_id: Optional[UUID] = None
    status: int

    model_config = ConfigDict(from_attributes=True)


@router.get("/process-devices", response_model=List[ProcessDeviceResponse])
async def list_process_devices(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await ProcessDeviceService.get_all(session, skip, limit)


@router.get("/process-devices/{obj_id}", response_model=ProcessDeviceResponse)
async def get_process_device(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    obj = await ProcessDeviceService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="ProcessDevice not found")
    return obj


@router.post("/process-devices", response_model=ProcessDeviceResponse)
async def create_process_device(
    item: ProcessDeviceCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await ProcessDeviceService.create(session, item.model_dump())


@router.put("/process-devices/{obj_id}", response_model=ProcessDeviceResponse)
async def update_process_device(
    obj_id: UUID,
    item: ProcessDeviceUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await ProcessDeviceService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="ProcessDevice not found")

    update_data = item.model_dump(exclude_unset=True)
    return await ProcessDeviceService.update(session, db_obj, update_data)


@router.delete("/process-devices/{obj_id}")
async def delete_process_device(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await ProcessDeviceService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="ProcessDevice not found")

    await ProcessDeviceService.delete(session, db_obj)
    return {"message": "ProcessDevice deleted successfully"}


# ==========================================
# 8. ProcessDeviceItem
# ==========================================
class ProcessDeviceItemCreate(BaseModel):
    code: str
    desc: str
    device_inst_id: UUID
    process_device_id: UUID


class ProcessDeviceItemUpdate(BaseModel):
    code: Optional[str] = None
    desc: Optional[str] = None
    device_inst_id: Optional[UUID] = None
    process_device_id: Optional[UUID] = None


class ProcessDeviceItemResponse(BaseModel):
    id: UUID
    code: str
    desc: str
    device_inst_id: UUID
    process_device_id: UUID

    model_config = ConfigDict(from_attributes=True)


@router.get("/process-device-items", response_model=List[ProcessDeviceItemResponse])
async def list_process_device_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await ProcessDeviceItemService.get_all(session, skip, limit)


@router.get("/process-device-items/{obj_id}", response_model=ProcessDeviceItemResponse)
async def get_process_device_item(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    obj = await ProcessDeviceItemService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="ProcessDeviceItem not found")
    return obj


@router.post("/process-device-items", response_model=ProcessDeviceItemResponse)
async def create_process_device_item(
    item: ProcessDeviceItemCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await ProcessDeviceItemService.create(session, item.model_dump())


@router.put("/process-device-items/{obj_id}", response_model=ProcessDeviceItemResponse)
async def update_process_device_item(
    obj_id: UUID,
    item: ProcessDeviceItemUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await ProcessDeviceItemService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="ProcessDeviceItem not found")

    update_data = item.model_dump(exclude_unset=True)
    return await ProcessDeviceItemService.update(session, db_obj, update_data)


@router.delete("/process-device-items/{obj_id}")
async def delete_process_device_item(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await ProcessDeviceItemService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="ProcessDeviceItem not found")

    await ProcessDeviceItemService.delete(session, db_obj)
    return {"message": "ProcessDeviceItem deleted successfully"}


# ==========================================
# 9. SensorMonitoring
# ==========================================
class SensorMonitoringCreate(BaseModel):
    device_inst_id: UUID
    location_id: Optional[UUID] = None
    sensor_id: Optional[UUID] = None
    direction: Optional[str] = None
    status: Optional[int] = 1


class SensorMonitoringUpdate(BaseModel):
    device_inst_id: Optional[UUID] = None
    location_id: Optional[UUID] = None
    sensor_id: Optional[UUID] = None
    direction: Optional[str] = None
    status: Optional[int] = None


class SensorMonitoringResponse(BaseModel):
    id: UUID
    device_inst_id: UUID
    location_id: Optional[UUID] = None
    sensor_id: Optional[UUID] = None
    direction: Optional[str] = None
    anomaly: int = 0
    ts: Optional[int] = None
    status: int

    model_config = ConfigDict(from_attributes=True)


@router.get("/sensor-monitorings", response_model=List[SensorMonitoringResponse])
async def list_sensor_monitorings(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    stmt = (
        select(SensorMonitoring)
        .join(DeviceInst, SensorMonitoring.device_inst_id == DeviceInst.id)
        .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
        .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
        .where(DeviceCategory.tenant_id == tenant_id)
        .offset(skip)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


class SensorMonitoringDeviceInstOption(BaseModel):
    id: UUID
    code: str
    sn: str
    device_spec_id: UUID

    model_config = ConfigDict(from_attributes=True)


class PagedDeviceInstResponse(BaseModel):
    items: List[SensorMonitoringDeviceInstOption]
    total: int


@router.get(
    "/sensor-monitorings/device-insts",
    response_model=PagedDeviceInstResponse,
)
async def list_sensor_monitoring_device_insts(
    current: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    base_join = (
        select(DeviceInst)
        .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
        .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
        .where(DeviceCategory.tenant_id == tenant_id)
    )
    if keyword:
        like = f"%{keyword}%"
        base_join = base_join.where(
            or_(DeviceInst.code.ilike(like), DeviceInst.sn.ilike(like))
        )

    # Count total
    count_stmt = select(func.count()).select_from(base_join.subquery())
    count_result = await session.execute(count_stmt)
    total = count_result.scalar() or 0

    # Fetch page
    skip = (current - 1) * pageSize
    fetch_stmt = base_join.offset(skip).limit(pageSize)
    result = await session.execute(fetch_stmt)
    items = result.scalars().all()

    return PagedDeviceInstResponse(items=items, total=total)


@router.get("/sensor-monitorings/{obj_id}", response_model=SensorMonitoringResponse)
async def get_sensor_monitoring(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    stmt = (
        select(SensorMonitoring)
        .join(DeviceInst, SensorMonitoring.device_inst_id == DeviceInst.id)
        .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
        .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
        .where(
            SensorMonitoring.id == obj_id,
            DeviceCategory.tenant_id == tenant_id,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="SensorMonitoring not found")
    return obj


@router.post("/sensor-monitorings", response_model=SensorMonitoringResponse)
async def create_sensor_monitoring(
    item: SensorMonitoringCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    payload = item.model_dump()
    await _validate_sensor_monitoring_refs(session, tenant_id, payload)
    return await SensorMonitoringService.create(session, payload)


@router.put("/sensor-monitorings/{obj_id}", response_model=SensorMonitoringResponse)
async def update_sensor_monitoring(
    obj_id: UUID,
    item: SensorMonitoringUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    stmt = (
        select(SensorMonitoring)
        .join(DeviceInst, SensorMonitoring.device_inst_id == DeviceInst.id)
        .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
        .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
        .where(
            SensorMonitoring.id == obj_id,
            DeviceCategory.tenant_id == tenant_id,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    db_obj = result.scalar_one_or_none()
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorMonitoring not found")

    update_data = item.model_dump(exclude_unset=True)
    await _validate_sensor_monitoring_refs(session, tenant_id, update_data)
    return await SensorMonitoringService.update(session, db_obj, update_data)


@router.delete("/sensor-monitorings/{obj_id}")
async def delete_sensor_monitoring(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(db_manager.get_session),
):
    tenant_id = current_account.tenant_id
    stmt = (
        select(SensorMonitoring)
        .join(DeviceInst, SensorMonitoring.device_inst_id == DeviceInst.id)
        .join(DeviceSpec, DeviceInst.device_spec_id == DeviceSpec.id)
        .join(DeviceCategory, DeviceSpec.device_category_id == DeviceCategory.id)
        .where(
            SensorMonitoring.id == obj_id,
            DeviceCategory.tenant_id == tenant_id,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    db_obj = result.scalar_one_or_none()
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorMonitoring not found")

    await SensorMonitoringService.delete(session, db_obj)
    return {"message": "SensorMonitoring deleted successfully"}

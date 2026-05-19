"""
Device related management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from uuid import UUID

from app.database import db_manager
from app.models.customer import Account as AccountModel
from app.services.device_service import (
    IsoStandardService,
    DeviceCategoryService,
    DeviceSpecService,
    DeviceInstService,
    DeviceComboSpecService,
    DeviceComboSpecItemService,
    DeviceComboInstService,
    DeviceComboInstItemService,
    DeviceInstTagService,
)
from app.utils.auth import get_current_account

router = APIRouter(tags=["devices"])


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
# 5. DeviceComboSpec
# ==========================================
class DeviceComboSpecCreate(BaseModel):
    tenant_id: Optional[UUID] = None
    code: str
    name: str
    status: Optional[int] = 1


class DeviceComboSpecUpdate(BaseModel):
    tenant_id: Optional[UUID] = None
    code: Optional[str] = None
    name: Optional[str] = None
    status: Optional[int] = None


class DeviceComboSpecResponse(BaseModel):
    id: UUID
    tenant_id: Optional[UUID] = None
    code: str
    name: str
    status: int

    model_config = ConfigDict(from_attributes=True)


@router.get("/device-combo-specs", response_model=List[DeviceComboSpecResponse])
async def list_device_combo_specs(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await DeviceComboSpecService.get_all(session, skip, limit)


@router.get("/device-combo-specs/{obj_id}", response_model=DeviceComboSpecResponse)
async def get_device_combo_spec(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    obj = await DeviceComboSpecService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="DeviceComboSpec not found")
    return obj


@router.post("/device-combo-specs", response_model=DeviceComboSpecResponse)
async def create_device_combo_spec(
    item: DeviceComboSpecCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await DeviceComboSpecService.create(session, item.model_dump())


@router.put("/device-combo-specs/{obj_id}", response_model=DeviceComboSpecResponse)
async def update_device_combo_spec(
    obj_id: UUID,
    item: DeviceComboSpecUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await DeviceComboSpecService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceComboSpec not found")

    update_data = item.model_dump(exclude_unset=True)
    return await DeviceComboSpecService.update(session, db_obj, update_data)


@router.delete("/device-combo-specs/{obj_id}")
async def delete_device_combo_spec(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await DeviceComboSpecService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceComboSpec not found")

    await DeviceComboSpecService.delete(session, db_obj)
    return {"message": "DeviceComboSpec deleted successfully"}


# ==========================================
# 6. DeviceComboSpecItem
# ==========================================
class DeviceComboSpecItemCreate(BaseModel):
    device_combo_id: UUID
    device_spec_id: UUID
    qty: Optional[int] = 1


class DeviceComboSpecItemUpdate(BaseModel):
    device_combo_id: Optional[UUID] = None
    device_spec_id: Optional[UUID] = None
    qty: Optional[int] = None


class DeviceComboSpecItemResponse(BaseModel):
    id: UUID
    device_combo_id: UUID
    device_spec_id: UUID
    qty: int

    model_config = ConfigDict(from_attributes=True)


@router.get("/device-combo-spec-items", response_model=List[DeviceComboSpecItemResponse])
async def list_device_combo_spec_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await DeviceComboSpecItemService.get_all(session, skip, limit)


@router.get("/device-combo-spec-items/{obj_id}", response_model=DeviceComboSpecItemResponse)
async def get_device_combo_spec_item(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    obj = await DeviceComboSpecItemService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="DeviceComboSpecItem not found")
    return obj


@router.post("/device-combo-spec-items", response_model=DeviceComboSpecItemResponse)
async def create_device_combo_spec_item(
    item: DeviceComboSpecItemCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await DeviceComboSpecItemService.create(session, item.model_dump())


@router.put("/device-combo-spec-items/{obj_id}", response_model=DeviceComboSpecItemResponse)
async def update_device_combo_spec_item(
    obj_id: UUID,
    item: DeviceComboSpecItemUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await DeviceComboSpecItemService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceComboSpecItem not found")

    update_data = item.model_dump(exclude_unset=True)
    return await DeviceComboSpecItemService.update(session, db_obj, update_data)


@router.delete("/device-combo-spec-items/{obj_id}")
async def delete_device_combo_spec_item(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await DeviceComboSpecItemService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceComboSpecItem not found")

    await DeviceComboSpecItemService.delete(session, db_obj)
    return {"message": "DeviceComboSpecItem deleted successfully"}


# ==========================================
# 7. DeviceComboInst
# ==========================================
class DeviceComboInstCreate(BaseModel):
    code: str
    device_combo_spec_id: UUID
    sn: str
    status: Optional[int] = 1


class DeviceComboInstUpdate(BaseModel):
    code: Optional[str] = None
    device_combo_spec_id: Optional[UUID] = None
    sn: Optional[str] = None
    status: Optional[int] = None


class DeviceComboInstResponse(BaseModel):
    id: UUID
    code: str
    device_combo_spec_id: UUID
    sn: str
    status: int

    model_config = ConfigDict(from_attributes=True)


@router.get("/device-combo-insts", response_model=List[DeviceComboInstResponse])
async def list_device_combo_insts(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await DeviceComboInstService.get_all(session, skip, limit)


@router.get("/device-combo-insts/{obj_id}", response_model=DeviceComboInstResponse)
async def get_device_combo_inst(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    obj = await DeviceComboInstService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="DeviceComboInst not found")
    return obj


@router.post("/device-combo-insts", response_model=DeviceComboInstResponse)
async def create_device_combo_inst(
    item: DeviceComboInstCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await DeviceComboInstService.create(session, item.model_dump())


@router.put("/device-combo-insts/{obj_id}", response_model=DeviceComboInstResponse)
async def update_device_combo_inst(
    obj_id: UUID,
    item: DeviceComboInstUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await DeviceComboInstService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceComboInst not found")

    update_data = item.model_dump(exclude_unset=True)
    return await DeviceComboInstService.update(session, db_obj, update_data)


@router.delete("/device-combo-insts/{obj_id}")
async def delete_device_combo_inst(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await DeviceComboInstService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceComboInst not found")

    await DeviceComboInstService.delete(session, db_obj)
    return {"message": "DeviceComboInst deleted successfully"}


# ==========================================
# 8. DeviceComboInstItem
# ==========================================
class DeviceComboInstItemCreate(BaseModel):
    code: str
    desc: str
    device_inst_id: UUID
    device_combo_inst_id: UUID


class DeviceComboInstItemUpdate(BaseModel):
    code: Optional[str] = None
    desc: Optional[str] = None
    device_inst_id: Optional[UUID] = None
    device_combo_inst_id: Optional[UUID] = None


class DeviceComboInstItemResponse(BaseModel):
    id: UUID
    code: str
    desc: str
    device_inst_id: UUID
    device_combo_inst_id: UUID

    model_config = ConfigDict(from_attributes=True)


@router.get("/device-combo-inst-items", response_model=List[DeviceComboInstItemResponse])
async def list_device_combo_inst_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await DeviceComboInstItemService.get_all(session, skip, limit)


@router.get("/device-combo-inst-items/{obj_id}", response_model=DeviceComboInstItemResponse)
async def get_device_combo_inst_item(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    obj = await DeviceComboInstItemService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="DeviceComboInstItem not found")
    return obj


@router.post("/device-combo-inst-items", response_model=DeviceComboInstItemResponse)
async def create_device_combo_inst_item(
    item: DeviceComboInstItemCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await DeviceComboInstItemService.create(session, item.model_dump())


@router.put("/device-combo-inst-items/{obj_id}", response_model=DeviceComboInstItemResponse)
async def update_device_combo_inst_item(
    obj_id: UUID,
    item: DeviceComboInstItemUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await DeviceComboInstItemService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceComboInstItem not found")

    update_data = item.model_dump(exclude_unset=True)
    return await DeviceComboInstItemService.update(session, db_obj, update_data)


@router.delete("/device-combo-inst-items/{obj_id}")
async def delete_device_combo_inst_item(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await DeviceComboInstItemService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceComboInstItem not found")

    await DeviceComboInstItemService.delete(session, db_obj)
    return {"message": "DeviceComboInstItem deleted successfully"}


# ==========================================
# 9. DeviceInstTag
# ==========================================
class DeviceInstTagCreate(BaseModel):
    device_inst_id: UUID
    point: str
    sensor_id: Optional[UUID] = None
    status: Optional[int] = 1


class DeviceInstTagUpdate(BaseModel):
    device_inst_id: Optional[UUID] = None
    point: Optional[str] = None
    sensor_id: Optional[UUID] = None
    status: Optional[int] = None


class DeviceInstTagResponse(BaseModel):
    id: UUID
    device_inst_id: UUID
    point: str
    sensor_id: Optional[UUID] = None
    status: int

    model_config = ConfigDict(from_attributes=True)


@router.get("/device-inst-tags", response_model=List[DeviceInstTagResponse])
async def list_device_inst_tags(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await DeviceInstTagService.get_all(session, skip, limit)


@router.get("/device-inst-tags/{obj_id}", response_model=DeviceInstTagResponse)
async def get_device_inst_tag(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    obj = await DeviceInstTagService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="DeviceInstTag not found")
    return obj


@router.post("/device-inst-tags", response_model=DeviceInstTagResponse)
async def create_device_inst_tag(
    item: DeviceInstTagCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await DeviceInstTagService.create(session, item.model_dump())


@router.put("/device-inst-tags/{obj_id}", response_model=DeviceInstTagResponse)
async def update_device_inst_tag(
    obj_id: UUID,
    item: DeviceInstTagUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await DeviceInstTagService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceInstTag not found")

    update_data = item.model_dump(exclude_unset=True)
    return await DeviceInstTagService.update(session, db_obj, update_data)


@router.delete("/device-inst-tags/{obj_id}")
async def delete_device_inst_tag(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await DeviceInstTagService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceInstTag not found")

    await DeviceInstTagService.delete(session, db_obj)
    return {"message": "DeviceInstTag deleted successfully"}

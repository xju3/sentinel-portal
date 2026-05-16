"""
Device related management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from uuid import UUID

from app.database import db_manager
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
    health_check_freq_id: UUID
    tenant_id: Optional[UUID] = None
    iso_standard_id: Optional[UUID] = None


class DeviceCategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    health_check_freq_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    iso_standard_id: Optional[UUID] = None


class DeviceCategoryResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    health_check_freq_id: UUID
    tenant_id: Optional[UUID] = None
    iso_standard_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


@router.get("/device-categories", response_model=List[DeviceCategoryResponse])
async def list_device_categories(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await DeviceCategoryService.get_all(session, skip, limit)


@router.get("/device-categories/{obj_id}", response_model=DeviceCategoryResponse)
async def get_device_category(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    obj = await DeviceCategoryService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="DeviceCategory not found")
    return obj


@router.post("/device-categories", response_model=DeviceCategoryResponse)
async def create_device_category(
    item: DeviceCategoryCreate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    return await DeviceCategoryService.create(session, item.model_dump())


@router.put("/device-categories/{obj_id}", response_model=DeviceCategoryResponse)
async def update_device_category(
    obj_id: UUID,
    item: DeviceCategoryUpdate,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await DeviceCategoryService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceCategory not found")

    update_data = item.model_dump(exclude_unset=True)
    return await DeviceCategoryService.update(session, db_obj, update_data)


@router.delete("/device-categories/{obj_id}")
async def delete_device_category(
    obj_id: UUID,
    session: AsyncSession = Depends(db_manager.get_session),
):
    db_obj = await DeviceCategoryService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceCategory not found")

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
    status: Optional[int] = 1


class DeviceInstUpdate(BaseModel):
    code: Optional[str] = None
    device_spec_id: Optional[UUID] = None
    sn: Optional[str] = None
    status: Optional[int] = None


class DeviceInstResponse(BaseModel):
    id: UUID
    code: str
    device_spec_id: UUID
    sn: str
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
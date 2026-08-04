"""
Device related management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, cast
from uuid import UUID
from pydantic import ValidationError

from pub.services import get_session
from pub.models.customer import Account as AccountModel
from pub.models.device import DeviceCategory, DeviceInst, DeviceSpec
from pub.models.sensor import SensorMonitoring
from pub.services import LocationService

from pub.services import (
    IsoStandardService,
    DeviceCategoryService,
    DeviceSpecService,
    BearingService,
    DeviceInstService,
    SupplierService,
    SensorMonitoringService,
    DashboardHealthService,
    DeviceHealthArchiveService,
    DevicePointTrendService,
    ProcessDeviceService,
)
from pub.decorators.dashboard_cache import rebuild_dashboard_cache
from pub.decorators.config_change import monitor_config_change

from app.utils.auth import get_current_account
from app.utils.response import success
from pub.contract.devices import (
    IsoStandardCreate,
    IsoStandardUpdate,
    IsoStandardResponse,
    DeviceCategoryCreate,
    DeviceCategoryUpdate,
    DeviceCategoryMembersUpdate,
    HealthCheckFreqBrief,
    DeviceCategoryResponse,
    PagedCountResponse,
    DeviceSpecCreate,
    DeviceSpecUpdate,
    DeviceSpecResponse,
    BearingModelCreate,
    BearingModelUpdate,
    BearingModelResponse,
    DeviceSpecBearingReplace,
    DeviceSpecBearingResponse,
    DeviceInstCreate,
    DeviceInstUpdate,
    DeviceInstResponse,
    SensorMonitoringCreate,
    SensorMonitoringUpdate,
    SensorMonitoringResponse,
    SensorMonitoringDeviceInstOption,
    PagedDeviceInstResponse,
)

import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["devices"])


# ==========================================
# Helper functions
# ==========================================

async def _require_tenant_device(
    session: AsyncSession,
    tenant_id: UUID,
    device_id: UUID,
):
    if not await DeviceInstService.is_tenant_device_inst(
        session,
        tenant_id,
        device_id,
    ):
        raise HTTPException(status_code=404, detail="Device not found")
    return await DeviceInstService.get_by_id(session, device_id)


async def _require_tenant_device_spec(
    session: AsyncSession,
    tenant_id: UUID,
    device_spec_id: UUID,
) -> None:
    if not await DeviceSpecService.is_tenant_device_spec(
        session,
        tenant_id,
        device_spec_id,
    ):
        raise HTTPException(status_code=400, detail="Device spec is not owned by current tenant")


async def _validate_device_spec_refs(
    session: AsyncSession,
    tenant_id: UUID,
    data: dict,
) -> None:
    device_category_id = data.get("device_category_id")
    if device_category_id is not None:
        category = await DeviceCategoryService.get_by_id(
            session,
            tenant_id,
            device_category_id,
        )
        if category is None:
            raise HTTPException(
                status_code=400,
                detail="device_category_id is not owned by current tenant",
            )

    supplier_id = data.get("supplier_id")
    if supplier_id is not None:
        supplier = await SupplierService.get_supplier(
            session,
            tenant_id,
            supplier_id,
        )
        if supplier is None:
            raise HTTPException(
                status_code=400,
                detail="supplier_id is not owned by current tenant",
            )


async def _validate_sensor_monitoring_refs(
    session: AsyncSession,
    tenant_id: UUID,
    data: dict,
) -> None:
    device_inst_id = data.get("device_inst_id")
    if device_inst_id is not None:
        ok = await DeviceInstService.is_tenant_device_inst(session, tenant_id, device_inst_id)
        if not ok:
            raise HTTPException(status_code=400, detail="device_inst_id is not owned by current tenant")

    location_id = data.get("location_id")
    if location_id is not None:
        ok = await LocationService.is_tenant_location(
            session,
            tenant_id,
            location_id,
            active_only=True,
        )
        if not ok:
            raise HTTPException(status_code=400, detail="location_id is not owned by current tenant")

    # sensor_id 校验已移除，传感器选择器已确保只显示可用传感器


# ==========================================
# 1. IsoStandard
# ==========================================
@router.get("/iso-standards")
async def list_iso_standards(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    session: AsyncSession = Depends(get_session),
):
    return success(await IsoStandardService.get_all(session, skip, limit, sort_by, sort_order))


@router.get("/iso-standards/{obj_id}")
async def get_iso_standard(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    obj = await IsoStandardService.get_by_id(session, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="IsoStandard not found")
    return success(obj)


@router.post("/iso-standards")
async def create_iso_standard(
    item: IsoStandardCreate,
    session: AsyncSession = Depends(get_session),
):
    return success(await IsoStandardService.create(session, item.model_dump()))


@router.put("/iso-standards/{obj_id}")
async def update_iso_standard(
    obj_id: UUID,
    item: IsoStandardUpdate,
    session: AsyncSession = Depends(get_session),
):
    db_obj = await IsoStandardService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="IsoStandard not found")

    update_data = item.model_dump(exclude_unset=True)
    return success(await IsoStandardService.update(session, db_obj, update_data))


@router.delete("/iso-standards/{obj_id}")
async def delete_iso_standard(
    obj_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    db_obj = await IsoStandardService.get_by_id(session, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="IsoStandard not found")

    await IsoStandardService.delete(session, db_obj)
    return success({"message": "IsoStandard deleted successfully"})


# ==========================================
# 2. DeviceCategory
# ==========================================
def _serialize_device_category(
    item,
    freq_obj=None,
) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "parent_id": item.parent_id,
        "health_check_freq_id": cast(Optional[UUID], item.health_check_freq_id),
        "tenant_id": cast(Optional[UUID], item.tenant_id),
        "iso_standard_id": cast(Optional[UUID], item.iso_standard_id),
        "vib_threshold_id": cast(Optional[UUID], item.vib_threshold_id),
        "temp_threshold_id": cast(Optional[UUID], item.temp_threshold_id),
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
        "employees": [
            {"id": e.id, "name": e.name} for e in getattr(item, "employees", [])
        ] if hasattr(item, "employees") else None,
        "iso_standard": (
            {
                "id": getattr(item, "iso_standard").id,
                "code": getattr(item, "iso_standard").code,
                "version": getattr(item, "iso_standard").version,
            }
            if hasattr(item, "iso_standard") and getattr(item, "iso_standard") is not None
            else None
        ),
        "vib_threshold": (
            {
                "id": getattr(item, "vib_threshold").id,
                "code": getattr(item, "vib_threshold").code,
            }
            if hasattr(item, "vib_threshold") and getattr(item, "vib_threshold") is not None
            else None
        ),
        "temp_threshold": (
            {
                "id": getattr(item, "temp_threshold").id,
                "code": getattr(item, "temp_threshold").code,
            }
            if hasattr(item, "temp_threshold") and getattr(item, "temp_threshold") is not None
            else None
        )
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


@router.get("/device-categories")
async def list_device_categories(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    rows = await DeviceCategoryService.get_all(session, tenant_id, skip, limit, keyword, sort_by, sort_order)
    freq_ids: List[UUID] = [cast(UUID, row.health_check_freq_id) for row in rows]
    freq_map = await DeviceCategoryService.get_health_check_freq_map(
        session,
        tenant_id,
        freq_ids,
    )
    return success([
        _serialize_device_category(row, freq_map.get(cast(UUID, row.health_check_freq_id)))
        for row in rows
    ])


@router.get("/device-categories/count")
async def count_device_categories(
    keyword: Optional[str] = Query(None),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    total = await DeviceCategoryService.count_all(session, tenant_id, keyword)
    return success({"total": total})


@router.get("/device-categories/{obj_id}")
async def get_device_category(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    obj = await DeviceCategoryService.get_by_id(session, tenant_id, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="DeviceCategory not found")
    freq_id = cast(UUID, obj.health_check_freq_id)
    freq_map = await DeviceCategoryService.get_health_check_freq_map(
        session,
        tenant_id,
        [freq_id],
    )
    return success(_serialize_device_category(obj, freq_map.get(freq_id)))


@router.post("/device-categories")
@rebuild_dashboard_cache()
async def create_device_category(
    item: DeviceCategoryCreate,
    background_tasks: BackgroundTasks,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    payload = item.model_dump(exclude_unset=True)
    if "tenant_id" in payload and payload["tenant_id"] is not None and payload["tenant_id"] != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id mismatch")
    payload["tenant_id"] = tenant_id
    await _validate_device_category_parent(session, tenant_id, payload.get("parent_id"))
    created = await DeviceCategoryService.create(session, payload)
    created_freq_id = cast(UUID, created.health_check_freq_id)
    freq_map = await DeviceCategoryService.get_health_check_freq_map(
        session,
        tenant_id,
        [created_freq_id],
    )
    return success(_serialize_device_category(created, freq_map.get(created_freq_id)))


@router.put("/device-categories/{obj_id}")
@monitor_config_change(DeviceCategory, "obj_id", "item")
@rebuild_dashboard_cache()
async def update_device_category(
    obj_id: UUID,
    item: DeviceCategoryUpdate,
    background_tasks: BackgroundTasks,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
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
    updated_freq_id = cast(UUID, updated.health_check_freq_id)
    freq_map = await DeviceCategoryService.get_health_check_freq_map(
        session,
        tenant_id,
        [updated_freq_id],
    )
    return success(_serialize_device_category(updated, freq_map.get(updated_freq_id)))


@router.post("/device-categories/{obj_id}/employees")
async def update_device_category_employees(
    obj_id: UUID,
    item: DeviceCategoryMembersUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_obj = await DeviceCategoryService.get_by_id(session, tenant_id, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceCategory not found")

    await DeviceCategoryService.update_members(session, tenant_id, db_obj, item.employee_ids)
    return success({"message": "Employees updated successfully"})


@router.delete("/device-categories/{obj_id}")
@rebuild_dashboard_cache()
async def delete_device_category(
    obj_id: UUID,
    background_tasks: BackgroundTasks,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
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
    return success({"message": "DeviceCategory deleted successfully"})


# ==========================================
# 3. Bearings
# ==========================================
@router.get("/bearings")
async def list_bearings(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    models = await BearingService.list_models(session, tenant_id, skip, limit)
    return success(
        [BearingModelResponse.model_validate(model) for model in models]
    )


@router.get("/bearings/{obj_id}")
async def get_bearing(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    obj = await BearingService.get_model(session, tenant_id, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Bearing model not found")
    return success(BearingModelResponse.model_validate(obj))


@router.post("/bearings")
async def create_bearing(
    item: BearingModelCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    data = item.model_dump()
    duplicate = await BearingService.find_duplicate(
        session, tenant_id, data["brand"], data["model"]
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail="A bearing with the same brand and model already exists",
        )
    try:
        created = await BearingService.create_model(session, tenant_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return success(BearingModelResponse.model_validate(created))


@router.put("/bearings/{obj_id}")
async def update_bearing(
    obj_id: UUID,
    item: BearingModelUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    obj = await BearingService.get_model(session, tenant_id, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Bearing model not found")

    update_data = item.model_dump(exclude_unset=True)
    merged = {
        "brand": obj.brand,
        "model": obj.model,
        "bearing_type": obj.bearing_type,
        "rolling_element_count": obj.rolling_element_count,
        "rolling_element_diameter_mm": obj.rolling_element_diameter_mm,
        "pitch_diameter_mm": obj.pitch_diameter_mm,
        "contact_angle_deg": obj.contact_angle_deg,
        "description": obj.description,
        "active": obj.active,
        **update_data,
    }
    try:
        validated = BearingModelCreate(**merged)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    normalized = validated.model_dump()
    update_data = {key: normalized[key] for key in update_data}

    duplicate = await BearingService.find_duplicate(
        session,
        tenant_id,
        normalized["brand"],
        normalized["model"],
        exclude_id=obj_id,
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail="A bearing with the same brand and model already exists",
        )
    try:
        updated = await BearingService.update_model(session, obj, update_data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return success(BearingModelResponse.model_validate(updated))


@router.delete("/bearings/{obj_id}")
async def delete_bearing(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    obj = await BearingService.get_model(session, tenant_id, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Bearing model not found")
    try:
        await BearingService.delete_model(session, obj)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return success({"message": "Bearing model deleted successfully"})


# ==========================================
# 4. DeviceSpec
# ==========================================
@router.get("/device-specs")
async def list_device_specs(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    process_device_id: Optional[UUID] = Query(None),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    return success(
        await DeviceSpecService.get_all(
            session,
            tenant_id,
            skip,
            limit,
            sort_by,
            sort_order,
            process_device_id,
        )
    )


@router.get("/device-specs/{obj_id}")
async def get_device_spec(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    obj = await DeviceSpecService.get_by_id(session, tenant_id, obj_id)
    if not obj:
        raise HTTPException(status_code=404, detail="DeviceSpec not found")
    return success(obj)


@router.get("/device-specs/{obj_id}/comparison")
async def get_device_spec_comparison(
    obj_id: UUID,
    process_device_id: UUID = Query(..., description="Device group to compare"),
    location_id: Optional[UUID] = Query(None, description="Monitoring point"),
    range_days: int = Query(3, description="Rolling range ending now"),
    window_minutes: Optional[int] = Query(None, ge=0),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    if await DeviceSpecService.get_by_id(session, tenant_id, obj_id) is None:
        raise HTTPException(status_code=404, detail="DeviceSpec not found")
    if (
        await ProcessDeviceService.get_by_id(
            session,
            tenant_id,
            process_device_id,
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Device group not found")
    try:
        comparison = await DevicePointTrendService.get_spec_comparison(
            session=session,
            tenant_id=tenant_id,
            device_spec_id=obj_id,
            process_device_id=process_device_id,
            location_id=location_id,
            range_days=range_days,
            window_minutes=window_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success(comparison)


@router.post("/device-specs")
@rebuild_dashboard_cache()
async def create_device_spec(
    item: DeviceSpecCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    data = item.model_dump()
    await _validate_device_spec_refs(session, tenant_id, data)
    return success(await DeviceSpecService.create(session, data))


@router.put("/device-specs/{obj_id}")
@monitor_config_change(DeviceSpec, "obj_id", "item")
@rebuild_dashboard_cache()
async def update_device_spec(
    obj_id: UUID,
    item: DeviceSpecUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_obj = await DeviceSpecService.get_by_id(session, tenant_id, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceSpec not found")

    update_data = item.model_dump(exclude_unset=True)
    await _validate_device_spec_refs(session, tenant_id, update_data)
    updated = await DeviceSpecService.update(session, db_obj, update_data)
    await BearingService.invalidate_diagnosis_cache(session, [obj_id])
    return success(updated)


@router.delete("/device-specs/{obj_id}")
@rebuild_dashboard_cache()
async def delete_device_spec(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_obj = await DeviceSpecService.get_by_id(session, tenant_id, obj_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="DeviceSpec not found")

    await DeviceSpecService.delete(session, db_obj)
    return success({"message": "DeviceSpec deleted successfully"})


@router.get("/device-specs/{obj_id}/bearings")
async def list_device_spec_bearings(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    bindings = await BearingService.list_bindings(session, tenant_id, obj_id)
    if bindings is None:
        raise HTTPException(status_code=404, detail="DeviceSpec not found")
    return success(
        [
            DeviceSpecBearingResponse.model_validate(binding)
            for binding in bindings
        ]
    )


@router.put("/device-specs/{obj_id}/bearings")
async def replace_device_spec_bearings(
    obj_id: UUID,
    item: DeviceSpecBearingReplace,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    try:
        bindings = await BearingService.replace_bindings(
            session,
            tenant_id,
            obj_id,
            [binding.model_dump() for binding in item.bindings],
        )
    except BearingService.ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if bindings is None:
        raise HTTPException(status_code=404, detail="DeviceSpec not found")
    return success(
        [
            DeviceSpecBearingResponse.model_validate(binding)
            for binding in bindings
        ]
    )


# ==========================================
# 5. DeviceInst
# ==========================================
@router.get("/device-insts")
async def list_device_insts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    current = skip // limit + 1
    items, _ = await DeviceInstService.get_tenant_device_insts_paged(
        session,
        tenant_id,
        current,
        limit,
    )
    return success(items)


@router.get("/device-insts/{obj_id}")
async def get_device_inst(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    return success(await _require_tenant_device(session, tenant_id, obj_id))


@router.post("/device-insts")
@rebuild_dashboard_cache()
async def create_device_inst(
    item: DeviceInstCreate,
    background_tasks: BackgroundTasks,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    await _require_tenant_device_spec(session, tenant_id, item.device_spec_id)
    return success(await DeviceInstService.create(session, item.model_dump()))


@router.put("/device-insts/{obj_id}")
@monitor_config_change(DeviceInst, "obj_id", "item")
@rebuild_dashboard_cache()
async def update_device_inst(
    obj_id: UUID,
    item: DeviceInstUpdate,
    background_tasks: BackgroundTasks,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_obj = await _require_tenant_device(session, tenant_id, obj_id)
    update_data = item.model_dump(exclude_unset=True)
    device_spec_id = update_data.get("device_spec_id")
    if device_spec_id is not None:
        await _require_tenant_device_spec(session, tenant_id, device_spec_id)
    return success(await DeviceInstService.update(session, db_obj, update_data))


@router.delete("/device-insts/{obj_id}")
@rebuild_dashboard_cache()
async def delete_device_inst(
    obj_id: UUID,
    background_tasks: BackgroundTasks,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_obj = await _require_tenant_device(session, tenant_id, obj_id)
    await DeviceInstService.delete(session, db_obj)
    return success({"message": "DeviceInst deleted successfully"})


# ==========================================
# 4b. Device Health Archive
# ==========================================
@router.get("/devices/{device_id}/health-archive")
async def get_device_health_archive(
    device_id: UUID,
    location_id: UUID | None = Query(
        None,
        description="Monitoring point; defaults to the first point for multi-point devices",
    ),
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
    current_account: AccountModel = Depends(get_current_account),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    device = await _require_tenant_device(session, tenant_id, device_id)
    points = await DeviceHealthArchiveService.get_device_points(
        session,
        tenant_id,
        device_id,
    )
    point_ids = {UUID(point["id"]) for point in points}
    selected_location_id = location_id
    if selected_location_id is not None and selected_location_id not in point_ids:
        raise HTTPException(status_code=404, detail="Monitoring point not found for device")
    if selected_location_id is None and points:
        selected_location_id = UUID(points[0]["id"])

    try:
        normalized_start, normalized_end = DeviceHealthArchiveService.normalize_range(
            start_at,
            end_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    timeline = await DeviceHealthArchiveService.get_timeline(
        session=session,
        tenant_id=tenant_id,
        device_id=device_id,
        start_at=normalized_start,
        end_at=normalized_end,
        interval_hours=interval_hours,
        location_id=selected_location_id,
    )
    timeline["device"] = {
        "id": str(device.id),
        "name": device.name,
        "code": device.code,
    }
    timeline["points"] = points
    timeline["selectedLocationId"] = (
        str(selected_location_id) if selected_location_id is not None else None
    )
    return success(timeline)


@router.get("/devices/{device_id}/point-trends")
async def get_device_point_trends(
    device_id: UUID,
    location_id: UUID = Query(..., description="Monitoring point to query"),
    range_days: int = Query(3, description="Rolling range ending at the current time"),
    window_minutes: int | None = Query(
        None,
        ge=0,
        description="Display aggregation window; 0 means raw data",
    ),
    session: AsyncSession = Depends(get_session),
    current_account: AccountModel = Depends(get_current_account),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    await _require_tenant_device(session, tenant_id, device_id)
    points = await DeviceHealthArchiveService.get_device_points(
        session,
        tenant_id,
        device_id,
    )
    if location_id not in {UUID(point["id"]) for point in points}:
        raise HTTPException(status_code=404, detail="Monitoring point not found for device")

    try:
        trend = await DevicePointTrendService.get_trends(
            session=session,
            tenant_id=tenant_id,
            device_id=device_id,
            location_id=location_id,
            range_days=range_days,
            window_minutes=window_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success(trend)


# ==========================================
# 4c. Devices - Fault list
# ==========================================
@router.get("/devices/faults")
async def list_fault_devices(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_account: AccountModel = Depends(get_current_account),
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


# ==========================================
# 5. SensorMonitoring
# ==========================================
@router.get("/sensor-monitorings")
async def list_sensor_monitorings(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    return success(await SensorMonitoringService.get_all_by_tenant(session, tenant_id, skip, limit, sort_by, sort_order))


@router.get(
    "/sensor-monitorings/device-insts",
)
async def list_sensor_monitoring_device_insts(
    current: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    items, total = await DeviceInstService.get_tenant_device_insts_paged(
        session, tenant_id, current, pageSize, keyword
    )
    return success(PagedDeviceInstResponse(items=items, total=total))


@router.get("/sensor-monitorings/{obj_id}")
async def get_sensor_monitoring(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    obj = await SensorMonitoringService.get_by_id_and_tenant(session, obj_id, tenant_id)
    if not obj:
        raise HTTPException(status_code=404, detail="SensorMonitoring not found")
    return success(obj)


@router.post("/sensor-monitorings")
@rebuild_dashboard_cache()
async def create_sensor_monitoring(
    item: SensorMonitoringCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    payload = item.model_dump()
    await _validate_sensor_monitoring_refs(session, tenant_id, payload)
    try:
        result = await SensorMonitoringService.create(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return success(result)


@router.put("/sensor-monitorings/{obj_id}")
@monitor_config_change(SensorMonitoring, "obj_id", "item")
@rebuild_dashboard_cache()
async def update_sensor_monitoring(
    obj_id: UUID,
    item: SensorMonitoringUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_obj = await SensorMonitoringService.get_by_id_and_tenant(session, obj_id, tenant_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorMonitoring not found")

    update_data = item.model_dump(exclude_unset=True)
    await _validate_sensor_monitoring_refs(session, tenant_id, update_data)
    try:
        result = await SensorMonitoringService.update(session, db_obj, update_data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return success(result)


@router.delete("/sensor-monitorings/{obj_id}")
@rebuild_dashboard_cache()
async def delete_sensor_monitoring(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_obj = await SensorMonitoringService.get_by_id_and_tenant(session, obj_id, tenant_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="SensorMonitoring not found")

    await SensorMonitoringService.delete(session, db_obj)
    return success({"message": "SensorMonitoring binding ended successfully"})

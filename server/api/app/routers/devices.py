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
from pub.models.device import DeviceCategory, DeviceInst, DeviceSpec, ProcessDeviceItem
from pub.models.sensor import SensorMonitoring
from pub.services import LocationService

from pub.services import (
    DeviceCategoryService,
    DeviceSpecService,
    BearingService,
    DeviceInstService,
    SupplierService,
    SensorMonitoringService,
    DashboardHealthService,
    DeviceHealthArchiveService,
    DevicePointTrendService,
    DeviceFftRecordService,
    ProcessDeviceService,
)
from pub.decorators.dashboard_cache import rebuild_dashboard_cache
from pub.decorators.config_change import monitor_config_change

from app.utils.auth import get_current_account
from app.utils.response import success
from pub.contract.devices import (
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
        "color": item.color,
        "parent_id": item.parent_id,
        "parent": (
            {"id": item.parent.id, "name": item.parent.name}
            if getattr(item, "parent", None) is not None
            else None
        ),
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
    limit: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    description: Optional[str] = Query(None),
    color: Optional[str] = Query(None),
    parent_id: Optional[UUID] = Query(None),
    health_check_freq_id: Optional[UUID] = Query(None),
    iso_standard_id: Optional[UUID] = Query(None),
    vib_threshold_id: Optional[UUID] = Query(None),
    temp_threshold_id: Optional[UUID] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    extra: dict = {}
    if keyword: extra["keyword"] = keyword
    if name: extra["name"] = name
    if description: extra["description"] = description
    if color: extra["color"] = color
    if parent_id is not None: extra["parent_id"] = parent_id
    if health_check_freq_id is not None:
        extra["health_check_freq_id"] = health_check_freq_id
    if iso_standard_id is not None: extra["iso_standard_id"] = iso_standard_id
    if vib_threshold_id is not None: extra["vib_threshold_id"] = vib_threshold_id
    if temp_threshold_id is not None: extra["temp_threshold_id"] = temp_threshold_id
    items, total = await DeviceCategoryService.get_device_categories(
        session, tenant_id, skip, limit, sort_by=sort_by, sort_order=sort_order, **extra
    )
    return success({"items": [
        _serialize_device_category(item, getattr(item, "health_check_freq", None))
        for item in items
    ], "total": total})


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
    limit: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    bearing_type: Optional[str] = Query(None),
    active: Optional[bool] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    extra: dict = {}
    if keyword: extra["keyword"] = keyword
    if brand: extra["brand"] = brand
    if model: extra["model"] = model
    if bearing_type: extra["bearing_type"] = bearing_type
    if active is not None: extra["active"] = active
    items, total = await BearingService.list_models(
        session, tenant_id, skip, limit, sort_by=sort_by, sort_order=sort_order, **extra
    )
    return success({"items": [BearingModelResponse.model_validate(item) for item in items], "total": total})


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
    limit: int = Query(20, ge=1, le=1000),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    name: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    supplier_id: Optional[UUID] = Query(None),
    device_category_id: Optional[UUID] = Query(None),
    rpm: Optional[int] = Query(None),
    voltage: Optional[float] = Query(None),
    process_device_id: Optional[UUID] = Query(None),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    specs, total = await DeviceSpecService.get_all(
        session,
        tenant_id,
        skip,
        limit,
        sort_by=sort_by,
        sort_order=sort_order,
        process_device_id=process_device_id,
        in_device_group=False,
        name=name,
        model=model,
        brand=brand,
        supplier_id=supplier_id,
        device_category_id=device_category_id,
        rpm=rpm,
        voltage=voltage,
    )
    return success({"items": specs, "total": total})

@router.get("/wx-mini-app/device-specs")
async def list_grouped_device_specs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    sort_by: Optional[str] = Query("name"),
    sort_order: Optional[str] = Query("ascend"),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    """小程序分组对比入口：分页返回至少属于一个设备分组的规格。"""
    tenant_id = cast(UUID, current_account.tenant_id)
    specs, total = await DeviceSpecService.get_all(
        session,
        tenant_id,
        skip,
        limit,
        sort_by,
        sort_order,
        in_device_group=True,
    )
    return success({"items": specs, "total": total})


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
    limit: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    code: Optional[str] = Query(None),
    purchase_date: Optional[str] = Query(None),
    life_span: Optional[int] = Query(None),
    desc: Optional[str] = Query(None),
    status: Optional[int] = Query(None),
    device_spec_id: Optional[UUID] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    items, total = await DeviceInstService.get_tenant_device_insts_paged(
        session,
        tenant_id,
        skip,
        limit,
        keyword=keyword,
        name=name,
        code=code,
        purchase_date=purchase_date,
        life_span=life_span,
        desc=desc,
        status=status,
        device_spec_id=device_spec_id,
        sort_by=sort_by,
        sort_order=sort_order or "ascend",
    )
    return success({"items": items, "total": total})


@router.get("/wx-mini-app/health-archive/devices")
async def list_wx_health_archive_devices(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    device_category_id: UUID | None = Query(None),
    device_spec_id: UUID | None = Query(None),
    process_device_id: UUID | None = Query(None),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    items, has_more = await DeviceInstService.get_tenant_health_archive_devices_paged(
        session=session,
        tenant_id=tenant_id,
        skip=skip,
        limit=limit,
        device_category_id=device_category_id,
        device_spec_id=device_spec_id,
        process_device_id=process_device_id,
    )
    return success({"items": items, "hasMore": has_more})


@router.get("/wx-mini-app/health-archive/device-filters")
async def list_wx_health_archive_device_filters(
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    return success(
        await DeviceInstService.get_tenant_health_archive_device_filters(
            session=session,
            tenant_id=tenant_id,
        )
    )


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
    device_spec = await DeviceSpecService.get_by_id(session, tenant_id, device.device_spec_id) if device.device_spec_id else None
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
        "rpm": device_spec.rpm if device_spec else 0,
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


@router.get("/devices/{device_id}/fft-records")
async def get_device_fft_records(
    device_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: AccountModel = Depends(get_current_account),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    await _require_tenant_device(session, tenant_id, device_id)
    records = await DeviceFftRecordService.list_for_device(
        session, tenant_id, device_id, limit=50
    )
    result = []
    for r in records:
        r_dict = {
            "id": r.id,
            "ts_ms": int(r.created_at.timestamp() * 1000) if r.created_at else r.ts_ms,
            "points": r.points,
            "range_g": r.range_g,
            "fs_hz": r.fs_hz,
        }
        result.append(r_dict)
    return success(result)


@router.get("/devices/{device_id}/fft-records/{record_id}/data")
async def get_device_fft_data(
    device_id: UUID,
    record_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_account: AccountModel = Depends(get_current_account),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    await _require_tenant_device(session, tenant_id, device_id)
    
    record = await DeviceFftRecordService.get_by_id(session, tenant_id, record_id)
    if not record or record.device_inst_id != device_id:
        raise HTTPException(status_code=404, detail="FFT record not found")

    import sys
    from pathlib import Path

    server_path = Path(__file__).parent.parent.parent.parent
    if str(server_path) not in sys.path:
        sys.path.append(str(server_path))

    from diagnosis.app.preparation.fft_parser import FftParser, build_preview_payload

    fft_data = FftParser.parse_from_minio(str(record.task_id))
    if not fft_data:
        raise HTTPException(status_code=404, detail="FFT binary data not found in storage")
        
    payload = build_preview_payload(fft_data)
    return success(payload)


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
    limit: int = Query(20, ge=1, le=200),
    device_inst_id: Optional[UUID] = Query(None),
    sensor_id: Optional[UUID] = Query(None),
    location_id: Optional[UUID] = Query(None),
    direction: Optional[str] = Query(None),
    status: Optional[int] = Query(None),
    anomaly: Optional[int] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    items, total = await SensorMonitoringService.get_all_by_tenant(
        session,
        tenant_id,
        skip,
        limit,
        sort_by,
        sort_order or "ascend",
        device_inst_id=device_inst_id,
        sensor_id=sensor_id,
        location_id=location_id,
        direction=direction,
        status=status,
        anomaly=anomaly,
    )
    return success({"items": items, "total": total})


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

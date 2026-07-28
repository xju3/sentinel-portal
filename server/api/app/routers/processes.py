"""Process template and process device management endpoints."""

from typing import Optional, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pub.contract.devices import (
    DeviceCategoryMembersUpdate,
    ProcessCreate,
    ProcessDeviceCreate,
    ProcessDeviceItemCreate,
    ProcessDeviceItemUpdate,
    ProcessDeviceUpdate,
    ProcessItemCreate,
    ProcessItemUpdate,
    ProcessUpdate,
)
from pub.decorators.config_change import monitor_config_change
from pub.decorators.dashboard_cache import rebuild_dashboard_cache
from pub.models.customer import Account as AccountModel
from pub.models.device import ProcessDevice, ProcessDeviceItem
from pub.services import (
    AreaService,
    DeviceInstService,
    DeviceSpecService,
    ProcessDeviceItemService,
    ProcessDeviceService,
    ProcessItemService,
    ProcessService,
    get_session,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.auth import get_current_account
from app.utils.response import success

router = APIRouter(tags=["processes"])


async def _validate_process_item_refs(
    session: AsyncSession,
    tenant_id: UUID,
    data: dict,
) -> None:
    process_id = data.get("process_id")
    if process_id is not None:
        process = await ProcessService.get_by_id(session, tenant_id, process_id)
        if process is None:
            raise HTTPException(
                status_code=400,
                detail="process_id is not owned by current tenant",
            )

    device_spec_id = data.get("device_spec_id")
    if device_spec_id is not None:
        owned = await DeviceSpecService.is_tenant_device_spec(
            session,
            tenant_id,
            device_spec_id,
        )
        if not owned:
            raise HTTPException(
                status_code=400,
                detail="device_spec_id is not owned by current tenant",
            )


async def _validate_process_device_refs(
    session: AsyncSession,
    tenant_id: UUID,
    data: dict,
) -> None:
    process_id = data.get("process_id")
    if process_id is not None:
        process = await ProcessService.get_by_id(session, tenant_id, process_id)
        if process is None:
            raise HTTPException(
                status_code=400,
                detail="process_id is not owned by current tenant",
            )

    area_id = data.get("area_id")
    if area_id is not None:
        area = await AreaService.get_area(session, tenant_id, area_id)
        if area is None:
            raise HTTPException(
                status_code=400,
                detail="area_id is not owned by current tenant",
            )


async def _validate_process_device_item_refs(
    session: AsyncSession,
    tenant_id: UUID,
    data: dict,
) -> None:
    process_device_id = data.get("process_device_id")
    if process_device_id is not None:
        process_device = await ProcessDeviceService.get_by_id(
            session,
            tenant_id,
            process_device_id,
        )
        if process_device is None:
            raise HTTPException(
                status_code=400,
                detail="process_device_id is not owned by current tenant",
            )

    device_inst_id = data.get("device_inst_id")
    if device_inst_id is not None:
        owned = await DeviceInstService.is_tenant_device_inst(
            session,
            tenant_id,
            device_inst_id,
        )
        if not owned:
            raise HTTPException(
                status_code=400,
                detail="device_inst_id is not owned by current tenant",
            )


@router.get("/processes")
async def list_processes(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    return success(
        await ProcessService.get_all(
            session,
            tenant_id,
            skip,
            limit,
            sort_by,
            sort_order,
        )
    )


@router.get("/processes/{obj_id}")
async def get_process(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    obj = await ProcessService.get_by_id(session, tenant_id, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Process not found")
    return success(obj)


@router.post("/processes")
async def create_process(
    item: ProcessCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    data = item.model_dump(exclude_unset=True)
    supplied_tenant_id = data.get("tenant_id")
    if supplied_tenant_id is not None and supplied_tenant_id != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id mismatch")
    data["tenant_id"] = tenant_id
    return success(await ProcessService.create(session, data))


@router.put("/processes/{obj_id}")
async def update_process(
    obj_id: UUID,
    item: ProcessUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_obj = await ProcessService.get_by_id(session, tenant_id, obj_id)
    if db_obj is None:
        raise HTTPException(status_code=404, detail="Process not found")

    data = item.model_dump(exclude_unset=True)
    if "tenant_id" in data and data["tenant_id"] != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id cannot be changed")
    data.pop("tenant_id", None)
    return success(await ProcessService.update(session, db_obj, data))


@router.delete("/processes/{obj_id}")
async def delete_process(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_obj = await ProcessService.get_by_id(session, tenant_id, obj_id)
    if db_obj is None:
        raise HTTPException(status_code=404, detail="Process not found")
    await ProcessService.delete(session, db_obj)
    return success({"message": "Process deleted successfully"})


@router.get("/process-items")
async def list_process_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    return success(
        await ProcessItemService.get_all(
            session,
            tenant_id,
            skip,
            limit,
            sort_by,
            sort_order,
        )
    )


@router.get("/process-items/{obj_id}")
async def get_process_item(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    obj = await ProcessItemService.get_by_id(session, tenant_id, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="ProcessItem not found")
    return success(obj)


@router.post("/process-items")
async def create_process_item(
    item: ProcessItemCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    data = item.model_dump()
    await _validate_process_item_refs(session, tenant_id, data)
    return success(await ProcessItemService.create(session, data))


@router.put("/process-items/{obj_id}")
async def update_process_item(
    obj_id: UUID,
    item: ProcessItemUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_obj = await ProcessItemService.get_by_id(session, tenant_id, obj_id)
    if db_obj is None:
        raise HTTPException(status_code=404, detail="ProcessItem not found")
    data = item.model_dump(exclude_unset=True)
    await _validate_process_item_refs(session, tenant_id, data)
    return success(await ProcessItemService.update(session, db_obj, data))


@router.delete("/process-items/{obj_id}")
async def delete_process_item(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_obj = await ProcessItemService.get_by_id(session, tenant_id, obj_id)
    if db_obj is None:
        raise HTTPException(status_code=404, detail="ProcessItem not found")
    await ProcessItemService.delete(session, db_obj)
    return success({"message": "ProcessItem deleted successfully"})


@router.get("/process-devices")
async def list_process_devices(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    return success(
        await ProcessDeviceService.get_all(
            session,
            tenant_id,
            skip,
            limit,
            sort_by,
            sort_order,
        )
    )


@router.get("/process-devices/{obj_id}")
async def get_process_device(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    obj = await ProcessDeviceService.get_by_id(session, tenant_id, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="ProcessDevice not found")
    return success(obj)


@router.post("/process-devices")
@rebuild_dashboard_cache()
async def create_process_device(
    item: ProcessDeviceCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    data = item.model_dump()
    await _validate_process_device_refs(session, tenant_id, data)
    return success(await ProcessDeviceService.create(session, data))


@router.put("/process-devices/{obj_id}")
@monitor_config_change(ProcessDevice, "obj_id", "item")
@rebuild_dashboard_cache()
async def update_process_device(
    obj_id: UUID,
    item: ProcessDeviceUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_obj = await ProcessDeviceService.get_by_id(session, tenant_id, obj_id)
    if db_obj is None:
        raise HTTPException(status_code=404, detail="ProcessDevice not found")
    data = item.model_dump(exclude_unset=True)
    await _validate_process_device_refs(session, tenant_id, data)
    return success(await ProcessDeviceService.update(session, db_obj, data))


@router.post("/process-devices/{obj_id}/employees")
async def update_process_device_employees(
    obj_id: UUID,
    item: DeviceCategoryMembersUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_obj = await ProcessDeviceService.get_by_id(session, tenant_id, obj_id)
    if db_obj is None:
        raise HTTPException(status_code=404, detail="ProcessDevice not found")
    await ProcessDeviceService.update_members(
        session,
        tenant_id,
        db_obj,
        item.employee_ids,
    )
    return success({"message": "Employees updated successfully"})


@router.delete("/process-devices/{obj_id}")
@rebuild_dashboard_cache()
async def delete_process_device(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_obj = await ProcessDeviceService.get_by_id(session, tenant_id, obj_id)
    if db_obj is None:
        raise HTTPException(status_code=404, detail="ProcessDevice not found")
    await ProcessDeviceService.delete(session, db_obj)
    return success({"message": "ProcessDevice deleted successfully"})


@router.get("/process-device-items")
async def list_process_device_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("ascend"),
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    return success(
        await ProcessDeviceItemService.get_all(
            session,
            tenant_id,
            skip,
            limit,
            sort_by,
            sort_order,
        )
    )


@router.get("/process-device-items/{obj_id}")
async def get_process_device_item(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    obj = await ProcessDeviceItemService.get_by_id(session, tenant_id, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="ProcessDeviceItem not found")
    return success(obj)


@router.post("/process-device-items")
@rebuild_dashboard_cache()
async def create_process_device_item(
    item: ProcessDeviceItemCreate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    data = item.model_dump()
    await _validate_process_device_item_refs(session, tenant_id, data)
    return success(await ProcessDeviceItemService.create(session, data))


@router.put("/process-device-items/{obj_id}")
@monitor_config_change(ProcessDeviceItem, "obj_id", "item")
@rebuild_dashboard_cache()
async def update_process_device_item(
    obj_id: UUID,
    item: ProcessDeviceItemUpdate,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_obj = await ProcessDeviceItemService.get_by_id(
        session,
        tenant_id,
        obj_id,
    )
    if db_obj is None:
        raise HTTPException(status_code=404, detail="ProcessDeviceItem not found")
    data = item.model_dump(exclude_unset=True)
    await _validate_process_device_item_refs(session, tenant_id, data)
    return success(
        await ProcessDeviceItemService.update(session, db_obj, data)
    )


@router.delete("/process-device-items/{obj_id}")
@rebuild_dashboard_cache()
async def delete_process_device_item(
    obj_id: UUID,
    current_account: AccountModel = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
):
    tenant_id = cast(UUID, current_account.tenant_id)
    db_obj = await ProcessDeviceItemService.get_by_id(
        session,
        tenant_id,
        obj_id,
    )
    if db_obj is None:
        raise HTTPException(status_code=404, detail="ProcessDeviceItem not found")
    await ProcessDeviceItemService.delete(session, db_obj)
    return success({"message": "ProcessDeviceItem deleted successfully"})

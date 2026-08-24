import inspect
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock
from uuid import uuid4

import pytest
from pub.contract.devices import ProcessCreate
from pub.models import import_all_models
from pub.models.device import Process
from pub.services import (
    ProcessDeviceItemService,
    ProcessDeviceService,
    ProcessItemService,
    ProcessService,
)

from app.main import app
from app.routers import processes

import_all_models()


def test_process_management_routes_are_registered():
    registered = {
        (route.path, method)
        for route in app.routes
        for method in route.methods or set()
    }
    expected = {
        ("/api/v1/processes", "GET"),
        ("/api/v1/processes", "POST"),
        ("/api/v1/processes/{obj_id}", "GET"),
        ("/api/v1/processes/{obj_id}", "PUT"),
        ("/api/v1/processes/{obj_id}", "DELETE"),
        ("/api/v1/process-items", "GET"),
        ("/api/v1/process-items", "POST"),
        ("/api/v1/process-items/{obj_id}", "PUT"),
        ("/api/v1/process-items/{obj_id}", "DELETE"),
        ("/api/v1/process-devices", "GET"),
        ("/api/v1/process-devices", "POST"),
        ("/api/v1/process-devices/{obj_id}", "PUT"),
        ("/api/v1/process-devices/{obj_id}", "DELETE"),
        ("/api/v1/process-devices/{obj_id}/employees", "POST"),
        ("/api/v1/process-device-items", "GET"),
        ("/api/v1/process-device-items", "POST"),
        ("/api/v1/process-device-items/{obj_id}", "PUT"),
        ("/api/v1/process-device-items/{obj_id}", "DELETE"),
    }

    assert expected <= registered


@pytest.mark.parametrize(
    ("route", "expected_names"),
    [
        (
            processes.list_processes,
            {"keyword", "code", "name", "status"},
        ),
        (
            processes.list_process_items,
            {"process_id", "device_spec_id"},
        ),
        (
            processes.list_process_devices,
            {"keyword", "code", "sn", "process_id", "area_id", "status", "device_spec_id"},
        ),
        (
            processes.list_process_device_items,
            {"code", "color", "desc", "process_device_id", "device_inst_id"},
        ),
    ],
)
def test_process_list_routes_default_limit_and_query_filters(route, expected_names):
    signature = inspect.signature(route)
    assert signature.parameters["limit"].default.default == 20
    assert expected_names <= set(signature.parameters)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "service",
    [
        ProcessService,
        ProcessItemService,
        ProcessDeviceService,
        ProcessDeviceItemService,
    ],
)
async def test_process_list_queries_are_tenant_scoped(service):
    tenant_id = uuid4()
    result = Mock()
    result.scalars.return_value.all.return_value = []
    session = Mock()
    session.execute = AsyncMock(return_value=result)

    await service.get_all(session, tenant_id, 0, 100)

    statement = session.execute.await_args_list[-1].args[0]
    assert "dg_template.tenant_id" in str(statement)
    assert tenant_id in statement.compile().params.values()


@pytest.mark.asyncio
async def test_device_group_list_can_filter_by_contained_device_spec():
    tenant_id = uuid4()
    device_spec_id = uuid4()
    result = Mock()
    result.scalars.return_value.all.return_value = []
    session = Mock()
    session.execute = AsyncMock(return_value=result)

    await ProcessDeviceService.get_all(
        session,
        tenant_id,
        0,
        100,
        device_spec_id=device_spec_id,
    )

    statement = session.execute.await_args_list[-1].args[0]
    sql = str(statement)
    assert "JOIN dg_inst_item" in sql
    assert "JOIN device_inst" in sql
    assert "device_inst.device_spec_id" in sql
    assert "dg_template.tenant_id" in sql
    assert device_spec_id in statement.compile().params.values()


@pytest.mark.asyncio
async def test_device_group_list_passes_device_spec_filter_to_service(monkeypatch):
    tenant_id = uuid4()
    device_spec_id = uuid4()
    session = Mock()
    get_all = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(processes.ProcessDeviceService, "get_all", get_all)

    await processes.list_process_devices(
        skip=0,
        limit=20,
        keyword="line-a",
        code="PD001",
        sn="SN-001",
        process_id=uuid4(),
        area_id=uuid4(),
        status=1,
        sort_by=None,
        sort_order="ascend",
        device_spec_id=device_spec_id,
        current_account=SimpleNamespace(tenant_id=tenant_id),
        session=session,
    )

    get_all.assert_awaited_once_with(
        session,
        tenant_id,
        0,
        20,
        None,
        "ascend",
        keyword="line-a",
        code="PD001",
        sn="SN-001",
        process_id=ANY,
        area_id=ANY,
        status=1,
        device_spec_id=device_spec_id,
    )


@pytest.mark.asyncio
async def test_process_list_passes_current_tenant_to_service(monkeypatch):
    tenant_id = uuid4()
    get_all = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(processes.ProcessService, "get_all", get_all)
    session = Mock()

    response = await processes.list_processes(
        skip=0,
        limit=20,
        keyword="kw",
        code="P001",
        name="主线",
        status=1,
        sort_by=None,
        sort_order="ascend",
        current_account=SimpleNamespace(tenant_id=tenant_id),
        session=session,
    )

    get_all.assert_awaited_once_with(
        session,
        tenant_id,
        0,
        20,
        None,
        "ascend",
        keyword="kw",
        code="P001",
        name="主线",
        status=1,
    )
    assert response.data == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_process_item_list_defaults_limit_and_passes_filters(monkeypatch):
    tenant_id = uuid4()
    process_id = uuid4()
    device_spec_id = uuid4()
    get_all = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(processes.ProcessItemService, "get_all", get_all)

    response = await processes.list_process_items(
        skip=0,
        limit=20,
        process_id=process_id,
        device_spec_id=device_spec_id,
        sort_by=None,
        sort_order="ascend",
        current_account=SimpleNamespace(tenant_id=tenant_id),
        session=Mock(),
    )

    get_all.assert_awaited_once_with(
        ANY,
        tenant_id,
        0,
        20,
        None,
        "ascend",
        process_id=process_id,
        device_spec_id=device_spec_id,
    )
    assert response.data == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_process_device_item_list_defaults_limit_and_passes_filters(monkeypatch):
    tenant_id = uuid4()
    process_device_id = uuid4()
    device_inst_id = uuid4()
    get_all = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(processes.ProcessDeviceItemService, "get_all", get_all)

    response = await processes.list_process_device_items(
        skip=0,
        limit=20,
        code="ITEM-01",
        color="red",
        desc="bearing",
        process_device_id=process_device_id,
        device_inst_id=device_inst_id,
        sort_by=None,
        sort_order="ascend",
        current_account=SimpleNamespace(tenant_id=tenant_id),
        session=Mock(),
    )

    get_all.assert_awaited_once_with(
        ANY,
        tenant_id,
        0,
        20,
        None,
        "ascend",
        code="ITEM-01",
        color="red",
        desc="bearing",
        process_device_id=process_device_id,
        device_inst_id=device_inst_id,
    )
    assert response.data == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_process_create_rejects_another_tenant():
    with pytest.raises(processes.HTTPException) as exc_info:
        await processes.create_process(
            item=ProcessCreate(
                tenant_id=uuid4(),
                code="P001",
                name="工段模板",
            ),
            current_account=SimpleNamespace(tenant_id=uuid4()),
            session=Mock(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "tenant_id mismatch"


def test_process_code_unique_constraint_is_tenant_scoped():
    constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in Process.__table__.constraints
        if constraint.name
    }

    assert constraints["uq_process_tenant_code"] == ("tenant_id", "code")
    assert Process.__table__.c.code.unique is not True


@pytest.mark.asyncio
async def test_process_code_lookup_is_tenant_scoped():
    tenant_id = uuid4()
    result = Mock()
    result.scalar_one_or_none.return_value = None
    session = Mock()
    session.execute = AsyncMock(return_value=result)

    await ProcessService.get_by_code(session, tenant_id, "PHM")

    statement = session.execute.await_args.args[0]
    sql = str(statement)
    params = statement.compile().params
    assert "dg_template.tenant_id" in sql
    assert "dg_template.code" in sql
    assert tenant_id in params.values()
    assert "PHM" in params.values()


@pytest.mark.asyncio
async def test_process_create_rejects_duplicate_code_in_current_tenant(monkeypatch):
    tenant_id = uuid4()
    monkeypatch.setattr(
        processes.ProcessService,
        "get_by_code",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    create = AsyncMock()
    monkeypatch.setattr(processes.ProcessService, "create", create)

    with pytest.raises(processes.HTTPException) as exc_info:
        await processes.create_process(
            item=ProcessCreate(code="PHM", name="工艺"),
            current_account=SimpleNamespace(tenant_id=tenant_id),
            session=Mock(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Process code already exists for current tenant"
    processes.ProcessService.get_by_code.assert_awaited_once_with(
        ANY,
        tenant_id,
        "PHM",
    )
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_create_allows_code_unused_by_current_tenant(monkeypatch):
    tenant_id = uuid4()
    get_by_code = AsyncMock(return_value=None)
    created = SimpleNamespace(
        id=uuid4(),
        tenant_id=tenant_id,
        code="PHM",
        name="工艺",
        status=1,
    )
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(processes.ProcessService, "get_by_code", get_by_code)
    monkeypatch.setattr(processes.ProcessService, "create", create)
    session = Mock()

    response = await processes.create_process(
        item=ProcessCreate(code="PHM", name="工艺"),
        current_account=SimpleNamespace(tenant_id=tenant_id),
        session=session,
    )

    get_by_code.assert_awaited_once_with(session, tenant_id, "PHM")
    create.assert_awaited_once_with(
        session,
        {
            "code": "PHM",
            "name": "工艺",
            "tenant_id": tenant_id,
        },
    )
    assert response.data["tenant_id"] == str(tenant_id)
    assert response.data["code"] == "PHM"


@pytest.mark.asyncio
async def test_process_item_rejects_another_tenant_process(monkeypatch):
    monkeypatch.setattr(
        processes.ProcessService,
        "get_by_id",
        AsyncMock(return_value=None),
    )

    with pytest.raises(processes.HTTPException) as exc_info:
        await processes._validate_process_item_refs(
            Mock(),
            uuid4(),
            {"process_id": uuid4()},
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "process_id is not owned by current tenant"

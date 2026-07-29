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

    statement = session.execute.await_args.args[0]
    assert "process.tenant_id" in str(statement)
    assert tenant_id in statement.compile().params.values()


@pytest.mark.asyncio
async def test_process_list_passes_current_tenant_to_service(monkeypatch):
    tenant_id = uuid4()
    get_all = AsyncMock(return_value=[])
    monkeypatch.setattr(processes.ProcessService, "get_all", get_all)
    session = Mock()

    await processes.list_processes(
        skip=0,
        limit=100,
        sort_by=None,
        sort_order="ascend",
        current_account=SimpleNamespace(tenant_id=tenant_id),
        session=session,
    )

    get_all.assert_awaited_once_with(
        session,
        tenant_id,
        0,
        100,
        None,
        "ascend",
    )


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
    assert "process.tenant_id" in sql
    assert "process.code" in sql
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

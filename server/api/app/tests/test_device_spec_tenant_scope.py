from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pub.models import import_all_models
from pub.services import DeviceCategoryService, DeviceSpecService

from app.routers import devices

import_all_models()


@pytest.mark.asyncio
async def test_device_spec_list_query_filters_by_category_tenant():
    tenant_id = uuid4()
    result = Mock()
    result.scalars.return_value.all.return_value = []
    session = Mock()
    session.execute = AsyncMock(return_value=result)

    await DeviceSpecService.get_all(session, tenant_id, 0, 100)

    statement = str(session.execute.await_args.args[0])
    assert "JOIN device_category" in statement
    assert "device_category.tenant_id" in statement


@pytest.mark.asyncio
async def test_device_spec_list_can_filter_by_tenant_owned_process_device():
    tenant_id = uuid4()
    process_device_id = uuid4()
    result = Mock()
    result.scalars.return_value.all.return_value = []
    session = Mock()
    session.execute = AsyncMock(return_value=result)

    await DeviceSpecService.get_all(
        session,
        tenant_id,
        0,
        100,
        process_device_id=process_device_id,
    )

    statement = session.execute.await_args.args[0]
    sql = str(statement)
    params = statement.compile().params.values()
    assert "JOIN device_inst" in sql
    assert "JOIN dg_inst_item" in sql
    assert "JOIN dg_inst" in sql
    assert "JOIN dg_template" in sql
    assert "dg_template.tenant_id" in sql
    assert tenant_id in params
    assert process_device_id in params


@pytest.mark.asyncio
async def test_device_spec_list_can_filter_to_specs_in_tenant_device_groups():
    tenant_id = uuid4()
    result = Mock()
    result.scalars.return_value.all.return_value = []
    session = Mock()
    session.execute = AsyncMock(return_value=result)

    await DeviceSpecService.get_all(
        session,
        tenant_id,
        20,
        10,
        in_device_group=True,
    )

    statement = session.execute.await_args.args[0]
    sql = str(statement)
    params = statement.compile().params
    assert "EXISTS" in sql
    assert "FROM dg_inst_item" in sql
    assert "JOIN device_inst" in sql
    assert "JOIN dg_inst" in sql
    assert "JOIN dg_template" in sql
    assert "dg_template.tenant_id" in sql
    assert tenant_id in params.values()
    assert 10 in params.values()
    assert 20 in params.values()


@pytest.mark.asyncio
async def test_device_spec_detail_query_filters_by_category_tenant():
    tenant_id = uuid4()
    result = Mock()
    result.scalar_one_or_none.return_value = None
    session = Mock()
    session.execute = AsyncMock(return_value=result)

    await DeviceSpecService.get_by_id(session, tenant_id, uuid4())

    statement = str(session.execute.await_args.args[0])
    assert "JOIN device_category" in statement
    assert "device_category.tenant_id" in statement


@pytest.mark.asyncio
async def test_device_spec_list_passes_current_tenant_to_service(monkeypatch):
    tenant_id = uuid4()
    get_all = AsyncMock(return_value=[])
    monkeypatch.setattr(devices.DeviceSpecService, "get_all", get_all)
    session = Mock()

    await devices.list_device_specs(
        skip=0,
        limit=100,
        sort_by=None,
        sort_order="ascend",
        process_device_id=None,
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
        None,
    )


@pytest.mark.asyncio
async def test_device_spec_list_passes_process_device_filter_to_service(monkeypatch):
    tenant_id = uuid4()
    process_device_id = uuid4()
    get_all = AsyncMock(return_value=[])
    monkeypatch.setattr(devices.DeviceSpecService, "get_all", get_all)
    session = Mock()

    await devices.list_device_specs(
        skip=0,
        limit=100,
        sort_by=None,
        sort_order="ascend",
        process_device_id=process_device_id,
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
        process_device_id,
    )


@pytest.mark.asyncio
async def test_mini_app_device_spec_list_requests_only_grouped_specs(monkeypatch):
    tenant_id = uuid4()
    get_all = AsyncMock(return_value=[])
    monkeypatch.setattr(devices.DeviceSpecService, "get_all", get_all)
    session = Mock()

    response = await devices.list_grouped_device_specs(
        skip=20,
        limit=10,
        sort_by="name",
        sort_order="ascend",
        current_account=SimpleNamespace(tenant_id=tenant_id),
        session=session,
    )

    get_all.assert_awaited_once_with(
        session,
        tenant_id,
        20,
        10,
        "name",
        "ascend",
        in_device_group=True,
    )
    assert response.data == []


@pytest.mark.asyncio
async def test_device_spec_comparison_validates_group_and_spec_tenant(monkeypatch):
    tenant_id = uuid4()
    spec_id = uuid4()
    group_id = uuid4()
    session = Mock()
    monkeypatch.setattr(
        devices.DeviceSpecService,
        "get_by_id",
        AsyncMock(return_value=SimpleNamespace(id=spec_id)),
    )
    monkeypatch.setattr(
        devices.ProcessDeviceService,
        "get_by_id",
        AsyncMock(return_value=SimpleNamespace(id=group_id)),
    )
    get_comparison = AsyncMock(return_value={"series": []})
    monkeypatch.setattr(
        devices.DevicePointTrendService,
        "get_spec_comparison",
        get_comparison,
    )

    await devices.get_device_spec_comparison(
        obj_id=spec_id,
        process_device_id=group_id,
        location_id=None,
        range_days=3,
        window_minutes=0,
        current_account=SimpleNamespace(tenant_id=tenant_id),
        session=session,
    )

    devices.DeviceSpecService.get_by_id.assert_awaited_once_with(
        session,
        tenant_id,
        spec_id,
    )
    devices.ProcessDeviceService.get_by_id.assert_awaited_once_with(
        session,
        tenant_id,
        group_id,
    )
    get_comparison.assert_awaited_once_with(
        session=session,
        tenant_id=tenant_id,
        device_spec_id=spec_id,
        process_device_id=group_id,
        location_id=None,
        range_days=3,
        window_minutes=0,
    )


@pytest.mark.asyncio
async def test_device_spec_refs_must_belong_to_current_tenant(monkeypatch):
    tenant_id = uuid4()
    category_id = uuid4()
    supplier_id = uuid4()
    monkeypatch.setattr(
        devices.DeviceCategoryService,
        "get_by_id",
        AsyncMock(return_value=SimpleNamespace(id=category_id)),
    )
    get_supplier = AsyncMock(return_value=None)
    monkeypatch.setattr(devices.SupplierService, "get_supplier", get_supplier)

    with pytest.raises(devices.HTTPException) as exc_info:
        await devices._validate_device_spec_refs(
            Mock(),
            tenant_id,
            {
                "device_category_id": category_id,
                "supplier_id": supplier_id,
            },
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "supplier_id is not owned by current tenant"


@pytest.mark.asyncio
async def test_device_category_update_explicitly_loads_employees_before_serialization():
    category = SimpleNamespace(name="旧名称")
    session = Mock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    updated = await DeviceCategoryService.update(
        session,
        category,
        {"name": "新名称"},
    )

    assert updated is category
    assert category.name == "新名称"
    session.commit.assert_awaited_once()
    assert session.refresh.await_args_list[0].args == (category,)
    assert session.refresh.await_args_list[1].args == (category,)
    assert session.refresh.await_args_list[1].kwargs == {
        "attribute_names": ["employees"],
    }

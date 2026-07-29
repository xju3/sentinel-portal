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

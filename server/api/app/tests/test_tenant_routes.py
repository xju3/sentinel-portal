import inspect
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.routers import customers


def test_tenant_list_route_defaults_limit_and_exposes_all_filters():
    signature = inspect.signature(customers.list_tenants)

    assert signature.parameters["limit"].default.default == 20
    assert {
        "active",
        "code",
        "name",
        "mqtt_server",
        "api_server",
        "status",
        "email_status",
        "industry",
        "email",
        "region_id",
        "sort_by",
        "sort_order",
    } <= set(signature.parameters)


@pytest.mark.asyncio
async def test_tenant_list_route_passes_filters_and_returns_paged_items(monkeypatch):
    session = object()
    tenant = SimpleNamespace(
        id=uuid4(),
        code="T001",
        name="Tenant A",
        mqtt_server="mqtt.example.com",
        api_server="api.example.com",
        region_id="330100",
        active=True,
        create_at=datetime(2026, 8, 24, 9, 0, 0),
        status=1,
        industry=3,
        email="ops@example.com",
        email_status=2,
        remark="工厂园区",
        web_site=None,
        desc=None,
        src=None,
    )
    get_tenants = AsyncMock(return_value=([tenant], 7))
    monkeypatch.setattr(customers.TenantService, "get_tenants", get_tenants)

    response = await customers.list_tenants(
        skip=20,
        limit=20,
        sort_by="name",
        sort_order="descend",
        active=True,
        code="T",
        name="Tenant",
        mqtt_server="mqtt",
        api_server="api",
        status=1,
        email_status=2,
        industry=3,
        email="ops@example.com",
        region_id="330100",
        session=session,
    )

    get_tenants.assert_awaited_once_with(
        session,
        20,
        20,
        "name",
        "descend",
        True,
        "T",
        "Tenant",
        "mqtt",
        "api",
        1,
        2,
        3,
        "ops@example.com",
        "330100",
    )
    assert response.data["total"] == 7
    assert response.data["items"][0]["code"] == "T001"

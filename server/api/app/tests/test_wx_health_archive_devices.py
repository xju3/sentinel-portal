from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.main import app
from app.routers import devices as devices_router
from app.utils.auth import get_current_account
from pub.services.device.device_inst_service import DeviceInstService


class _RowsResult:
    def __init__(self, *, rows=None):
        self._rows = rows or []

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, results):
        self._results = iter(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return next(self._results)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_tenant_health_archive_devices_paged_builds_filtered_stable_query():
    tenant_id = uuid4()
    device_id = uuid4()
    spec_id = uuid4()
    category_id = uuid4()
    process_device_id = uuid4()
    last_monitored_at = datetime(2026, 8, 15, 8, 30, tzinfo=timezone.utc)
    session = _FakeSession(
        [
            _RowsResult(
                rows=[
                    SimpleNamespace(
                        id=device_id,
                        name="循环泵",
                        code="P-001",
                        desc="A line",
                        status=1,
                        active=1,
                        available=1,
                        device_spec_id=spec_id,
                        device_spec_name="泵",
                        device_spec_model="X1",
                        device_spec_brand="BrandA",
                        device_category_id=category_id,
                        device_category_name="泵类",
                        device_category_color="#00FF00",
                        active_binding_count=2,
                        historical_point_count=3,
                        last_monitored_at=last_monitored_at,
                    )
                ]
            ),
        ]
    )

    items, has_more = await DeviceInstService.get_tenant_health_archive_devices_paged(
        session=session,
        tenant_id=tenant_id,
        skip=10,
        limit=5,
        device_category_id=category_id,
        device_spec_id=spec_id,
        process_device_id=process_device_id,
    )

    assert items == [
        {
            "id": device_id,
            "name": "循环泵",
            "code": "P-001",
            "desc": "A line",
            "status": 1,
            "active": 1,
            "available": 1,
            "deviceSpec": {
                "id": spec_id,
                "name": "泵",
                "model": "X1",
                "brand": "BrandA",
            },
            "deviceCategory": {
                "id": category_id,
                "name": "泵类",
                "color": "#00FF00",
            },
            "activeBindingCount": 2,
            "historicalPointCount": 3,
            "lastMonitoredAt": last_monitored_at,
        }
    ]
    assert has_more is False

    fetch_stmt = session.statements[0]
    fetch_sql = str(fetch_stmt)
    compiled = fetch_stmt.compile()

    assert "FROM sensor_monitoring" in fetch_sql
    assert "JOIN location ON location.id = sensor_monitoring.location_id" in fetch_sql
    assert "sensor_monitoring.sensor_id IS NOT NULL" in fetch_sql
    assert "location.tenant_id" in fetch_sql
    assert "GROUP BY sensor_monitoring.device_inst_id" in fetch_sql
    assert "device_category.tenant_id" in fetch_sql
    assert "device_category.id" in fetch_sql
    assert "device_spec.id" in fetch_sql
    assert "EXISTS" in fetch_sql
    assert "dg_inst_item" in fetch_sql
    assert "dg_inst" in fetch_sql
    assert "dg_template" in fetch_sql
    assert "ORDER BY device_inst.name ASC, device_inst.id ASC" in fetch_sql
    assert tenant_id in compiled.params.values()
    assert category_id in compiled.params.values()
    assert spec_id in compiled.params.values()
    assert process_device_id in compiled.params.values()
    assert 10 in compiled.params.values()
    assert 6 in compiled.params.values()


@pytest.mark.asyncio
async def test_get_tenant_health_archive_device_filters_returns_linked_options():
    tenant_id = uuid4()
    category_id = uuid4()
    spec_id = uuid4()
    other_spec_id = uuid4()
    group_id = uuid4()
    session = _FakeSession(
        [
            _RowsResult(rows=[SimpleNamespace(id=category_id, name="泵类")]),
            _RowsResult(
                rows=[
                    SimpleNamespace(
                        id=spec_id,
                        name="离心泵",
                        device_category_id=category_id,
                    )
                ]
            ),
            _RowsResult(
                rows=[
                    SimpleNamespace(
                        id=group_id,
                        code="G-01",
                        process_name="循环水泵组",
                        device_spec_id=spec_id,
                    ),
                    SimpleNamespace(
                        id=group_id,
                        code="G-01",
                        process_name="循环水泵组",
                        device_spec_id=other_spec_id,
                    ),
                ]
            ),
        ]
    )

    result = await DeviceInstService.get_tenant_health_archive_device_filters(
        session=session,
        tenant_id=tenant_id,
    )

    assert result == {
        "categories": [{"id": category_id, "name": "泵类"}],
        "specs": [
            {
                "id": spec_id,
                "name": "离心泵",
                "deviceCategoryId": category_id,
            }
        ],
        "groups": [
            {
                "id": group_id,
                "name": "循环水泵组",
                "deviceSpecIds": [spec_id, other_spec_id],
            }
        ],
    }
    assert len(session.statements) == 3
    assert all(
        tenant_id in statement.compile().params.values()
        for statement in session.statements
    )


@pytest.mark.asyncio
async def test_wx_health_archive_device_filters_route_returns_service_data(monkeypatch):
    tenant_id = uuid4()
    category_id = uuid4()
    spec_id = uuid4()
    group_id = uuid4()
    session = object()
    expected = {
        "categories": [{"id": category_id, "name": "泵类"}],
        "specs": [
            {
                "id": spec_id,
                "name": "离心泵",
                "deviceCategoryId": category_id,
            }
        ],
        "groups": [
            {
                "id": group_id,
                "name": "循环水泵组",
                "deviceSpecIds": [spec_id],
            }
        ],
    }
    captured = {}

    async def fake_get_filters(*, session, tenant_id):
        captured["session"] = session
        captured["tenant_id"] = tenant_id
        return expected

    async def _fake_session_dependency():
        yield session

    monkeypatch.setattr(
        devices_router.DeviceInstService,
        "get_tenant_health_archive_device_filters",
        fake_get_filters,
    )
    app.dependency_overrides[get_current_account] = lambda: SimpleNamespace(
        tenant_id=tenant_id
    )
    app.dependency_overrides[devices_router.get_session] = _fake_session_dependency

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/wx-mini-app/health-archive/device-filters"
        )

    assert response.status_code == 200
    assert captured == {"session": session, "tenant_id": tenant_id}
    assert response.json()["data"] == {
        "categories": [{"id": str(category_id), "name": "泵类"}],
        "specs": [
            {
                "id": str(spec_id),
                "name": "离心泵",
                "deviceCategoryId": str(category_id),
            }
        ],
        "groups": [
            {
                "id": str(group_id),
                "name": "循环水泵组",
                "deviceSpecIds": [str(spec_id)],
            }
        ],
    }


@pytest.mark.asyncio
async def test_wx_health_archive_devices_route_uses_tenant_scoped_service(monkeypatch):
    tenant_id = uuid4()
    device_id = uuid4()
    captured: dict[str, object] = {}

    async def fake_get_devices(
        *,
        session,
        tenant_id,
        skip,
        limit,
        device_category_id,
        device_spec_id,
        process_device_id,
    ):
        captured["session"] = session
        captured["tenant_id"] = tenant_id
        captured["skip"] = skip
        captured["limit"] = limit
        captured["device_category_id"] = device_category_id
        captured["device_spec_id"] = device_spec_id
        captured["process_device_id"] = process_device_id
        return (
            [
                {
                "id": device_id,
                "name": "循环泵",
                "code": "P-001",
                "desc": None,
                "status": 1,
                "active": 1,
                "available": 1,
                "deviceSpec": {
                    "id": uuid4(),
                    "name": "泵",
                    "model": "X1",
                    "brand": "BrandA",
                },
                "deviceCategory": {
                    "id": uuid4(),
                    "name": "泵类",
                    "color": "#00FF00",
                },
                "activeBindingCount": 1,
                "historicalPointCount": 2,
                "lastMonitoredAt": datetime(
                    2026, 8, 15, 8, 30, tzinfo=timezone.utc
                ),
                }
            ],
            False,
        )

    async def _fake_session_dependency():
        yield object()

    monkeypatch.setattr(
        devices_router.DeviceInstService,
        "get_tenant_health_archive_devices_paged",
        fake_get_devices,
    )
    app.dependency_overrides[get_current_account] = lambda: SimpleNamespace(
        tenant_id=tenant_id
    )
    app.dependency_overrides[devices_router.get_session] = _fake_session_dependency
    category_id = uuid4()
    spec_id = uuid4()
    process_device_id = uuid4()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/wx-mini-app/health-archive/devices",
            params={
                "skip": 20,
                "limit": 10,
                "device_category_id": str(category_id),
                "device_spec_id": str(spec_id),
                "process_device_id": str(process_device_id),
            },
        )

    assert response.status_code == 200
    assert captured["tenant_id"] == tenant_id
    assert captured["skip"] == 20
    assert captured["limit"] == 10
    assert captured["device_category_id"] == category_id
    assert captured["device_spec_id"] == spec_id
    assert captured["process_device_id"] == process_device_id
    payload = response.json()["data"]
    assert payload["hasMore"] is False
    assert payload["items"][0]["id"] == str(device_id)


@pytest.mark.asyncio
async def test_wx_health_archive_devices_route_rejects_limit_over_100():
    async def _fake_session_dependency():
        yield object()

    app.dependency_overrides[get_current_account] = lambda: SimpleNamespace(
        tenant_id=uuid4()
    )
    app.dependency_overrides[devices_router.get_session] = _fake_session_dependency

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/wx-mini-app/health-archive/devices",
            params={"limit": 101},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] != 0
    assert "less than or equal to 100" in payload["message"]

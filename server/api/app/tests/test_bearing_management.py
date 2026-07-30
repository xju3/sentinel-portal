from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.routers import devices
from pub.contract.devices import (
    BearingModelCreate,
    BearingModelUpdate,
    DeviceSpecBearingInput,
    DeviceSpecBearingReplace,
)
from pub.models.device import BearingModel, DeviceSpecBearing
from pub.services.device.bearing_service import BearingService


def _bearing_payload() -> dict:
    return {
        "brand": "SKF",
        "model": "6205-2RS",
        "rolling_element_count": 9,
        "rolling_element_diameter_mm": 7.9,
        "pitch_diameter_mm": 39.0,
        "contact_angle_deg": 0.0,
    }


def test_bearing_geometry_rejects_element_larger_than_pitch_diameter():
    payload = _bearing_payload()
    payload["rolling_element_diameter_mm"] = 40.0

    with pytest.raises(ValidationError, match="must be less than"):
        BearingModelCreate(**payload)


def test_bearing_geometry_rejects_non_finite_values():
    payload = _bearing_payload()
    payload["pitch_diameter_mm"] = float("inf")

    with pytest.raises(ValidationError, match="finite number"):
        BearingModelCreate(**payload)


def test_bearing_contract_rejects_unknown_type_option():
    payload = _bearing_payload()
    payload["bearing_type"] = "CUSTOM_TYPE"

    with pytest.raises(ValidationError, match="Input should be"):
        BearingModelCreate(**payload)


def test_binding_contract_rejects_duplicate_locations():
    bearing_id = uuid4()
    location_id = uuid4()

    with pytest.raises(ValidationError, match="locations must be unique"):
        DeviceSpecBearingReplace(
            bindings=[
                DeviceSpecBearingInput(
                    bearing_id=bearing_id,
                    location_id=location_id,
                ),
                DeviceSpecBearingInput(
                    bearing_id=bearing_id,
                    location_id=location_id,
                ),
            ]
        )


def test_binding_contract_rejects_nonpositive_shaft_speed_ratio():
    with pytest.raises(ValidationError, match="greater than 0"):
        DeviceSpecBearingInput(
            bearing_id=uuid4(),
            location_id=uuid4(),
            shaft_speed_ratio=0,
        )


@pytest.mark.asyncio
async def test_bearing_list_query_is_tenant_scoped():
    tenant_id = uuid4()
    result = Mock()
    result.scalars.return_value.all.return_value = []
    session = Mock()
    session.execute = AsyncMock(return_value=result)

    await BearingService.list_models(session, tenant_id)

    statement = str(session.execute.await_args.args[0])
    assert "bearing_model.tenant_id" in statement


@pytest.mark.asyncio
async def test_replace_bindings_rejects_bearing_from_another_tenant(monkeypatch):
    tenant_id = uuid4()
    spec_id = uuid4()
    foreign_bearing_id = uuid4()
    location_id = uuid4()
    monkeypatch.setattr(
        devices.DeviceSpecService,
        "is_tenant_device_spec",
        AsyncMock(return_value=True),
    )
    # BearingService imports the same DeviceSpecService class object.
    owned_result = Mock()
    owned_result.scalars.return_value.all.return_value = []
    session = Mock()
    session.execute = AsyncMock(return_value=owned_result)
    session.commit = AsyncMock()

    with pytest.raises(ValueError, match="owned by current tenant"):
        await BearingService.replace_bindings(
            session,
            tenant_id,
            spec_id,
            [
                {
                    "bearing_id": foreign_bearing_id,
                    "location_id": location_id,
                    "shaft_speed_ratio": 1.0,
                    "enabled": True,
                }
            ],
        )

    session.add_all.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_replace_bindings_commits_one_complete_replacement(monkeypatch):
    tenant_id = uuid4()
    spec_id = uuid4()
    bearing_id = uuid4()
    location_id = uuid4()
    monkeypatch.setattr(
        devices.DeviceSpecService,
        "is_tenant_device_spec",
        AsyncMock(return_value=True),
    )
    owned_bearing_result = Mock()
    owned_bearing_result.scalars.return_value.all.return_value = [bearing_id]
    owned_location_result = Mock()
    owned_location_result.scalars.return_value.all.return_value = [location_id]
    session = Mock()
    session.execute = AsyncMock(
        side_effect=[owned_bearing_result, owned_location_result, Mock()]
    )
    session.commit = AsyncMock()
    monkeypatch.setattr(
        BearingService,
        "invalidate_diagnosis_cache",
        AsyncMock(),
    )
    expected = [SimpleNamespace(location_id=location_id)]
    monkeypatch.setattr(BearingService, "list_bindings", AsyncMock(return_value=expected))

    result = await BearingService.replace_bindings(
        session,
        tenant_id,
        spec_id,
        [
            {
                "bearing_id": bearing_id,
                "location_id": location_id,
                "shaft_speed_ratio": 0.2,
                "enabled": True,
            }
        ],
    )

    assert result == expected
    added = session.add_all.call_args.args[0]
    assert len(added) == 1
    assert isinstance(added[0], DeviceSpecBearing)
    assert added[0].device_spec_id == spec_id
    session.commit.assert_awaited_once()
    BearingService.invalidate_diagnosis_cache.assert_awaited_once_with(
        session, [spec_id]
    )


@pytest.mark.asyncio
async def test_binding_change_invalidates_sn_and_device_context_keys(monkeypatch):
    device_id = uuid4()
    device_result = Mock()
    device_result.scalars.return_value.all.return_value = [device_id]
    sensor_result = Mock()
    sensor_result.scalars.return_value.all.return_value = ["SN-001"]
    session = Mock()
    session.execute = AsyncMock(side_effect=[device_result, sensor_result])
    redis_client = Mock()
    monkeypatch.setattr(
        "pub.services.device.bearing_service.redis_manager.get_client",
        Mock(return_value=redis_client),
    )

    await BearingService.invalidate_diagnosis_cache(session, [uuid4()])

    deleted_keys = set(redis_client.delete.call_args.args)
    assert deleted_keys == {
        "dia:diagnosis_context:SN-001",
        f"dia:device_context:{device_id}",
    }


@pytest.mark.asyncio
async def test_binding_response_uses_explicit_dto_without_recursive_relationships(
    monkeypatch,
):
    tenant_id = uuid4()
    spec_id = uuid4()
    bearing = BearingModel(
        id=uuid4(),
        tenant_id=tenant_id,
        brand="SKF",
        model="6205",
        rolling_element_count=9,
        rolling_element_diameter_mm=7.9,
        pitch_diameter_mm=39.0,
        contact_angle_deg=0.0,
        active=True,
    )
    binding = DeviceSpecBearing(
        id=uuid4(),
        device_spec_id=spec_id,
        bearing_id=bearing.id,
        location_id=uuid4(),
        shaft_speed_ratio=0.2,
        enabled=True,
    )
    binding.bearing = bearing
    binding.location = SimpleNamespace(id=binding.location_id, name="减速机输出端")
    monkeypatch.setattr(
        devices.BearingService,
        "list_bindings",
        AsyncMock(return_value=[binding]),
    )

    response = await devices.list_device_spec_bearings(
        obj_id=spec_id,
        current_account=SimpleNamespace(tenant_id=tenant_id),
        session=Mock(),
    )

    assert response.data == [
        {
            "bearing_id": str(bearing.id),
            "location_id": str(binding.location_id),
            "shaft_speed_ratio": 0.2,
            "enabled": True,
            "id": str(binding.id),
            "device_spec_id": str(spec_id),
            "bearing": {
                "brand": "SKF",
                "model": "6205",
                "bearing_type": None,
                "rolling_element_count": 9,
                "rolling_element_diameter_mm": 7.9,
                "pitch_diameter_mm": 39.0,
                "contact_angle_deg": 0.0,
                "description": None,
                "active": True,
                "id": str(bearing.id),
                "tenant_id": str(tenant_id),
            },
            "location": {
                "id": str(binding.location_id),
                "name": "减速机输出端",
            },
        }
    ]


@pytest.mark.asyncio
async def test_update_revalidates_geometry_against_existing_values(monkeypatch):
    tenant_id = uuid4()
    bearing_id = uuid4()
    bearing = SimpleNamespace(
        id=bearing_id,
        brand="SKF",
        model="6205",
        bearing_type=None,
        rolling_element_count=9,
        rolling_element_diameter_mm=7.9,
        pitch_diameter_mm=39.0,
        contact_angle_deg=0.0,
        description=None,
        active=True,
    )
    monkeypatch.setattr(
        devices.BearingService,
        "get_model",
        AsyncMock(return_value=bearing),
    )

    with pytest.raises(devices.HTTPException) as exc_info:
        await devices.update_bearing(
            obj_id=bearing_id,
            item=BearingModelUpdate(rolling_element_diameter_mm=40.0),
            current_account=SimpleNamespace(tenant_id=tenant_id),
            session=Mock(),
        )

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_get_bindings_returns_404_for_foreign_device_spec(monkeypatch):
    monkeypatch.setattr(
        devices.BearingService,
        "list_bindings",
        AsyncMock(return_value=None),
    )

    with pytest.raises(devices.HTTPException) as exc_info:
        await devices.list_device_spec_bearings(
            obj_id=uuid4(),
            current_account=SimpleNamespace(tenant_id=uuid4()),
            session=Mock(),
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_device_spec_update_invalidates_diagnosis_context(monkeypatch):
    tenant_id = uuid4()
    spec_id = uuid4()
    existing = SimpleNamespace(id=spec_id, rpm=1450)
    updated = SimpleNamespace(id=spec_id, rpm=1500)
    monkeypatch.setattr(
        devices.DeviceSpecService,
        "get_by_id",
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr(
        devices.DeviceSpecService,
        "update",
        AsyncMock(return_value=updated),
    )
    monkeypatch.setattr(
        devices.BearingService,
        "invalidate_diagnosis_cache",
        AsyncMock(),
    )
    session = Mock()

    response = await devices.update_device_spec.__wrapped__.__wrapped__(
        obj_id=spec_id,
        item=devices.DeviceSpecUpdate(rpm=1500),
        current_account=SimpleNamespace(tenant_id=tenant_id),
        session=session,
    )

    assert response.data["rpm"] == 1500
    devices.BearingService.invalidate_diagnosis_cache.assert_awaited_once_with(
        session,
        [spec_id],
    )

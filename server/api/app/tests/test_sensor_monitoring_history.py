from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from pub.models.sensor import SensorMonitoring
from pub.services.sensor.sensor_db_service import SensorDbService
from pub.services.sensor.sensor_monitoring_service import SensorMonitoringService


class _FakeSession:
    def __init__(self):
        self.added = []
        self.commit_count = 0
        self.flush_count = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commit_count += 1

    async def flush(self):
        self.flush_count += 1

    async def refresh(self, _obj):
        return None


class _EmptyResult:
    def first(self):
        return None


class _CaptureQuerySession:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _EmptyResult()


def _binding(*, status: int = 1):
    return SimpleNamespace(
        id=uuid4(),
        device_inst_id=uuid4(),
        location_id=uuid4(),
        sensor_id=uuid4(),
        direction="horizontal",
        status=status,
        bound_at=datetime(2026, 8, 1),
        unbound_at=None,
    )


@pytest.mark.asyncio
async def test_binding_change_closes_old_row_and_creates_replacement(monkeypatch):
    session = _FakeSession()
    old_binding = _binding()
    new_location_id = uuid4()
    ensure_available = AsyncMock()
    notify = AsyncMock()
    monkeypatch.setattr(
        SensorMonitoringService,
        "_ensure_active_binding_available",
        ensure_available,
    )
    monkeypatch.setattr(
        SensorMonitoringService,
        "_notify_binding_sensors",
        notify,
    )

    replacement = await SensorMonitoringService.update(
        session,
        old_binding,
        {"location_id": new_location_id, "status": 1},
    )

    assert old_binding.status == 0
    assert old_binding.unbound_at is not None
    assert isinstance(replacement, SensorMonitoring)
    assert replacement.location_id == new_location_id
    assert replacement.status == 1
    assert replacement.unbound_at is None
    assert session.added == [replacement]
    assert session.commit_count == 1
    ensure_available.assert_awaited_once()
    notify.assert_awaited_once_with(
        session,
        {old_binding.sensor_id},
        {old_binding.device_inst_id},
    )


@pytest.mark.asyncio
async def test_delete_ends_binding_without_deleting_history(monkeypatch):
    session = _FakeSession()
    binding = _binding()
    notify = AsyncMock()
    monkeypatch.setattr(
        SensorMonitoringService,
        "_notify_binding_sensors",
        notify,
    )

    await SensorMonitoringService.delete(session, binding)

    assert binding.status == 0
    assert binding.unbound_at is not None
    assert session.commit_count == 1
    assert session.added == []
    notify.assert_awaited_once_with(
        session,
        {binding.sensor_id},
        {binding.device_inst_id},
    )


@pytest.mark.asyncio
async def test_historical_binding_cannot_be_rewritten():
    session = _FakeSession()
    historical = _binding(status=0)

    with pytest.raises(ValueError, match="read-only"):
        await SensorMonitoringService.update(
            session,
            historical,
            {"location_id": uuid4(), "status": 0},
        )

    assert session.commit_count == 0
    assert session.added == []


@pytest.mark.asyncio
async def test_delayed_sample_metadata_query_uses_binding_effective_period():
    session = _CaptureQuerySession()

    await SensorDbService.get_sensor_metadata_for_cache(
        session,
        "SN-001",
        sampled_at_ms=1_786_060_800_000,
    )

    statement = str(session.statement)
    assert "sensor_monitoring.bound_at <=" in statement
    assert "sensor_monitoring.unbound_at IS NULL" in statement
    assert "sensor_monitoring.unbound_at >" in statement


class _ScalarRows:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _TupleRows:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


@pytest.mark.asyncio
async def test_binding_change_invalidates_all_binding_dependent_caches(monkeypatch):
    sensor_id = uuid4()
    device_id = uuid4()
    process_device_id = uuid4()
    device_category_id = uuid4()
    session = Mock()
    session.execute = AsyncMock(
        side_effect=[
            _ScalarRows(["SN-001"]),
            _TupleRows([(process_device_id, device_category_id)]),
        ]
    )
    redis_client = Mock()
    monkeypatch.setattr(
        "pub.manager.database.redis_manager.get_client",
        Mock(return_value=redis_client),
    )
    create_task = AsyncMock()
    monkeypatch.setattr(
        "pub.services.sensor.sensor_task_service.create_manual_sensor_task",
        create_task,
    )

    await SensorMonitoringService._notify_binding_sensors(
        session,
        {sensor_id},
        {device_id},
    )

    assert set(redis_client.delete.call_args.args) == {
        "sensor_meta:SN-001",
        "dia:diagnosis_context:SN-001",
        f"dia:device_context:{device_id}",
        f"dia:peer_group:{process_device_id}:{device_category_id}",
    }
    create_task.assert_awaited_once()

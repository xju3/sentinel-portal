from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI

from app.routers import register_routers, sensors as sensors_router
from pub.contract.sensors import SensorTaskCreate
from pub.models import import_all_models
from pub.models.sensor import Sensor
from pub.services import (
    SENSOR_TASK_STATUS_DONE,
    complete_device_system_task,
    create_manual_sensor_task,
    list_sensor_tasks,
    record_sensor_status,
    record_sensor_task_report,
)

import_all_models()


def test_device_task_completion_routes_support_current_and_versioned_firmware():
    app = FastAPI()
    register_routers(app)
    paths = app.openapi()["paths"]

    current_operation = paths["/sensors/{task_id}/complete/{status}"]["post"]
    versioned_operation = paths["/api/v1/sensors/{task_id}/complete/{status}"]["post"]
    assert "requestBody" not in current_operation
    assert "requestBody" not in versioned_operation
    assert "/api/v1/sensors/tasks/{task_id}/complete/{status}" not in paths


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "expected_success"), [(1, True), (0, False)])
async def test_complete_sensor_system_task_status_mapping(
    monkeypatch, status, expected_success
):
    task_id = uuid4()
    task = SimpleNamespace(
        id=task_id,
        name="update_binding",
        sn="STL26SH0001",
        action=3,
        val=0,
        remark=None,
        status=1 if expected_success else 3,
        create_time=datetime.now(),
        dispatched_at=None,
        complete_time=None,
    )
    captured = {}

    async def fake_complete_device_system_task(**kwargs):
        captured.update(kwargs)
        return task

    monkeypatch.setattr(
        sensors_router,
        "complete_device_system_task",
        fake_complete_device_system_task,
    )

    await sensors_router.complete_sensor_system_task(
        task_id=task_id,
        status=status,
        session=Mock(),
    )

    assert captured["success"] is expected_success
    assert "sn" not in captured


@pytest.mark.asyncio
async def test_create_manual_sensor_task_uses_selected_sensor_and_starts_pending():
    sensor_id = uuid4()
    sensor = SimpleNamespace(id=sensor_id, sn="STL26SH0001")
    session = Mock()
    session.get = AsyncMock(return_value=sensor)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    task = await create_manual_sensor_task(
        session=session,
        sensor_id=sensor_id,
        name="现场复测",
        action=15,
        val=3,
        remark="确认温度变化",
    )

    session.get.assert_awaited_once_with(Sensor, sensor_id)
    session.add.assert_called_once_with(task)
    assert task.sn == "STL26SH0001"
    assert task.status == 0


@pytest.mark.asyncio
async def test_create_manual_sensor_task_rejects_missing_sensor():
    session = Mock()
    session.get = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="Sensor not found"):
        await create_manual_sensor_task(
            session=session,
            sensor_id=uuid4(),
            name="现场复测",
            action=15,
            val=3,
        )

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_list_sensor_tasks_does_not_change_task_state():
    task = SimpleNamespace(status=0)
    count_result = Mock()
    count_result.scalar_one.return_value = 1
    list_result = Mock()
    list_result.scalars.return_value.all.return_value = [task]
    session = Mock()
    session.execute = AsyncMock(side_effect=[count_result, list_result])
    session.commit = AsyncMock()

    items, total = await list_sensor_tasks(session=session, current=1, page_size=10)

    assert items == [task]
    assert total == 1
    assert task.status == 0
    session.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "field,value",
    [("action", 10), ("action", 100), ("action", 10000), ("val", -1)],
)
def test_sensor_task_create_rejects_invalid_action_and_val(field, value):
    payload = {
        "sensor_id": uuid4(),
        "name": "现场复测",
        "action": 15,
        "val": 3,
    }
    payload[field] = value

    with pytest.raises(ValueError):
        SensorTaskCreate(**payload)


def test_sensor_task_create_accepts_firmware_task_with_zero_val():
    payload = SensorTaskCreate(
        sensor_id=uuid4(),
        name="固件升级",
        action=0,
        val=0,
    )

    assert payload.action == 0
    assert payload.val == 0


def test_sensor_task_create_rejects_collection_task_with_zero_val():
    with pytest.raises(ValueError):
        SensorTaskCreate(sensor_id=uuid4(), name="特征采集", action=15, val=0)


def test_sensor_task_create_rejects_blank_name():
    with pytest.raises(ValueError):
        SensorTaskCreate(sensor_id=uuid4(), name="   ", action=15, val=3)


@pytest.mark.asyncio
async def test_complete_device_system_task_uses_task_id_and_validates_action():
    task_id = uuid4()
    task = SimpleNamespace(id=task_id, sn="STL26SH0001", action=0, status=2, complete_time=None)
    result = Mock()
    result.scalar_one_or_none.return_value = task
    session = Mock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    completed = await complete_device_system_task(
        session=session,
        task_id=task_id,
    )

    assert completed is task
    assert task.status == SENSOR_TASK_STATUS_DONE
    assert task.complete_time is not None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_complete_device_system_task_accepts_binding_task():
    task = SimpleNamespace(id=uuid4(), sn="STL26SH0001", action=3, status=2)
    result = Mock()
    result.scalar_one_or_none.return_value = task
    session = Mock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    completed = await complete_device_system_task(
        session=session,
        task_id=task.id,
    )

    assert completed is task
    assert task.status == SENSOR_TASK_STATUS_DONE
    assert task.complete_time is not None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_complete_device_system_task_rejects_status_task():
    task = SimpleNamespace(id=uuid4(), sn="STL26SH0001", action=2, status=2)
    result = Mock()
    result.scalar_one_or_none.return_value = task
    session = Mock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    completed = await complete_device_system_task(
        session=session,
        task_id=task.id,
    )

    assert completed is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_device_system_task_rejects_missing_task():
    result = Mock()
    result.scalar_one_or_none.return_value = None
    session = Mock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    completed = await complete_device_system_task(
        session=session,
        task_id=uuid4(),
    )

    assert completed is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_feature_report_cannot_complete_another_task_category():
    task = SimpleNamespace(id=uuid4(), sn="STL26SH0001", action=3, status=2, val=1)
    result = Mock()
    result.scalar_one_or_none.return_value = task
    session = Mock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    completed = await record_sensor_task_report(
        session=session,
        task_id=task.id,
        sn=task.sn,
        sequence=1,
        report_id="report-1",
        ts_ms=1780814415097,
    )

    assert completed is None
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_feature_report_cannot_complete_another_sensor_task():
    task = SimpleNamespace(id=uuid4(), sn="STL26SH0001", action=15, status=2, val=1)
    result = Mock()
    result.scalar_one_or_none.return_value = task
    session = Mock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    completed = await record_sensor_task_report(
        session=session,
        task_id=task.id,
        sn="STL26SH9999",
        sequence=1,
        report_id="report-1",
        ts_ms=1780814415097,
    )

    assert completed is None
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_status_report_persists_and_completes_matching_status_task():
    task_id = uuid4()
    task = SimpleNamespace(id=task_id, sn="STL26SH0001", action=2, status=2, complete_time=None)
    result = Mock()
    result.scalar_one_or_none.return_value = task
    session = Mock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    status = await record_sensor_status(
        session=session,
        sn="STL26SH0001",
        ts_ms=1780814415097,
        temperature=42.5,
        rssi=-78,
        voltage=91,
        task_id=task_id,
    )

    session.add.assert_called_once_with(status)
    assert status.sn == task.sn
    assert task.status == SENSOR_TASK_STATUS_DONE
    session.commit.assert_awaited_once()

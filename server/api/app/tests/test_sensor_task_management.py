from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from pub.contract.sensors import SensorTaskCreate
from pub.models import import_all_models
from pub.models.sensor import Sensor
from pub.services.sensor_task_service import create_manual_sensor_task, list_sensor_tasks

import_all_models()


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
    [("action", 0), ("action", 10), ("action", 100), ("action", 10000), ("val", 0)],
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


def test_sensor_task_create_rejects_blank_name():
    with pytest.raises(ValueError):
        SensorTaskCreate(sensor_id=uuid4(), name="   ", action=15, val=3)

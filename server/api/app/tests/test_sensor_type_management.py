from unittest.mock import AsyncMock, Mock

import pytest

from pub.contract.sensors import SensorTypeCreate, SensorTypeUpdate
from pub.models.sensor import SensorType
from pub.services import SensorTypeService


def test_sensor_type_contracts_use_battery_field():
    create_data = SensorTypeCreate(name="S1", battery=19000).model_dump()
    update_data = SensorTypeUpdate(battery=20000).model_dump(exclude_unset=True)

    assert create_data["battery"] == 19000
    assert "voltage" not in create_data
    assert update_data == {"battery": 20000}


@pytest.mark.asyncio
async def test_create_sensor_type_accepts_battery():
    session = Mock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    sensor_type = await SensorTypeService.create(
        session,
        SensorTypeCreate(name="S1", battery=19000).model_dump(),
    )

    assert isinstance(sensor_type, SensorType)
    assert sensor_type.name == "S1"
    assert sensor_type.battery == 19000
    session.add.assert_called_once_with(sensor_type)
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(sensor_type)

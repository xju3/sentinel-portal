from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from pub.services.diagnosis.device_point_trend_service import (
    DevicePointTrendService,
)


def test_default_windows_and_raw_range_guard():
    assert DevicePointTrendService.normalize_options(3, None, 1) == (3, 0)
    assert DevicePointTrendService.normalize_options(7, None, 60) == (7, 60)
    assert DevicePointTrendService.normalize_options(14, None, 60) == (14, 120)

    with pytest.raises(ValueError, match="three-day"):
        DevicePointTrendService.normalize_options(7, 0, 60)


def test_window_never_drops_below_configured_patrol_frequency():
    assert DevicePointTrendService.normalize_options(7, 60, 90) == (7, 90)


def test_flux_query_is_scoped_to_device_and_location_and_groups_sensor_history():
    device_id = uuid4()
    location_id = uuid4()
    query = DevicePointTrendService.build_flux_query(
        bucket="features",
        device_id=device_id,
        location_id=location_id,
        start_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
        window_minutes=60,
    )

    assert f'r.device_id == "{device_id}"' in query
    assert f'r.location_id == "{location_id}"' in query
    assert 'group(columns: ["_field"])' in query
    assert "aggregateWindow(every: 60m" in query
    assert "max_rms_vel" in query


class _Record:
    def __init__(self, field, value, result="value", device_id=None):
        self._field = field
        self._value = value
        self.values = {"result": result}
        if device_id is not None:
            self.values["device_id"] = str(device_id)

    def get_field(self):
        return self._field

    def get_value(self):
        return self._value

    def get_time(self):
        return datetime(2026, 8, 4, 8, tzinfo=timezone.utc)


def test_parse_aggregated_records_preserves_min_max_last_and_count():
    records = [
        _Record("temperature", 30.5, "mean"),
        _Record("temperature", 29.0, "min"),
        _Record("temperature", 32.0, "max"),
        _Record("temperature", 31.0, "last"),
        _Record("temperature", 4, "count"),
        _Record("max_rms_vel", 2.4, "mean"),
        _Record("max_rms_vel", 1.2, "min"),
        _Record("max_rms_vel", 4.8, "max"),
        _Record("max_rms_vel", 2.0, "last"),
        _Record("max_rms_vel", 4, "count"),
    ]

    result = DevicePointTrendService.parse_records(
        [SimpleNamespace(records=records)],
        aggregated=True,
    )

    assert result["temperature"][0] == {
        "value": 30.5,
        "min": 29.0,
        "max": 32.0,
        "last": 31.0,
        "count": 4,
    }
    assert result["vibration"][0]["max"] == 4.8


def test_parse_raw_records_keeps_actual_values():
    result = DevicePointTrendService.parse_records(
        [SimpleNamespace(records=[_Record("temperature", 26.25)])],
        aggregated=False,
    )

    assert result["temperature"][0]["value"] == 26.25
    assert result["temperature"][0]["count"] == 1
    assert result["vibration"] == [None]


def test_group_flux_query_reads_all_devices_in_one_query():
    device_ids = [uuid4(), uuid4()]
    location_id = uuid4()

    query = DevicePointTrendService.build_group_flux_query(
        bucket="features",
        device_ids=device_ids,
        location_id=location_id,
        start_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
        window_minutes=60,
    )

    assert "contains(value: r.device_id" in query
    assert str(device_ids[0]) in query
    assert str(device_ids[1]) in query
    assert f'r.location_id == "{location_id}"' in query
    assert 'group(columns: ["device_id", "_field"])' in query


def test_parse_group_records_keeps_device_series_separate():
    first_device_id = uuid4()
    second_device_id = uuid4()
    records = [
        _Record("temperature", 25.0, device_id=first_device_id),
        _Record("temperature", 31.5, device_id=second_device_id),
        _Record("max_rms_vel", 2.4, device_id=second_device_id),
    ]

    result = DevicePointTrendService.parse_group_records(
        [SimpleNamespace(records=records)],
        aggregated=False,
    )

    assert result[str(first_device_id)]["temperature"][0]["value"] == 25.0
    assert result[str(first_device_id)]["vibration"] == [None]
    assert result[str(second_device_id)]["temperature"][0]["value"] == 31.5
    assert result[str(second_device_id)]["vibration"][0]["value"] == 2.4


@pytest.mark.asyncio
async def test_comparison_locations_preserve_the_device_dimension():
    tenant_id = uuid4()
    first_device_id = uuid4()
    second_device_id = uuid4()
    first_location_id = uuid4()
    second_location_id = uuid4()
    result = Mock()
    result.all.return_value = [
        SimpleNamespace(
            id=first_location_id,
            name="驱动端",
            device_inst_id=first_device_id,
            status=1,
        ),
        SimpleNamespace(
            id=first_location_id,
            name="驱动端",
            device_inst_id=second_device_id,
            status=0,
        ),
        SimpleNamespace(
            id=second_location_id,
            name="非驱动端",
            device_inst_id=second_device_id,
            status=1,
        ),
    ]
    session = SimpleNamespace(execute=AsyncMock(return_value=result))

    locations, location_devices = (
        await DevicePointTrendService._get_comparison_locations(
            session=session,
            tenant_id=tenant_id,
            device_ids=[first_device_id, second_device_id],
        )
    )

    by_id = {item["id"]: item for item in locations}
    assert by_id[str(first_location_id)]["deviceCount"] == 2
    assert by_id[str(first_location_id)]["activeDeviceCount"] == 1
    assert location_devices[first_location_id] == {
        first_device_id,
        second_device_id,
    }
    assert location_devices[second_location_id] == {second_device_id}

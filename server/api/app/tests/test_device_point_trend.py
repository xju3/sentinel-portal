from datetime import datetime, timezone
from types import SimpleNamespace
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
    def __init__(self, field, value, result="value"):
        self._field = field
        self._value = value
        self.values = {"result": result}

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

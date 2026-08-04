from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pub.models.diagnosis import DiagnosisRecordStatus
from pub.services.diagnosis.device_health_archive_service import (
    DeviceHealthArchiveService,
)


def _record(ts_ms: int, status: DiagnosisRecordStatus, level: int | None = None):
    return SimpleNamespace(
        ts_ms=ts_ms,
        diagnosis_status=int(status),
        overall_level=level,
    )


def test_timeline_uses_highest_health_level_and_preserves_gap():
    result = DeviceHealthArchiveService.build_timeline(
        records=[
            _record(1_000, DiagnosisRecordStatus.DIAGNOSED, 0),
            _record(2_000, DiagnosisRecordStatus.DIAGNOSED, 2),
            _record(3_000, DiagnosisRecordStatus.MISSED),
        ],
        start_ms=0,
        end_ms=3_600_000,
        interval_ms=3_600_000,
    )

    bucket = result["buckets"][0]
    assert bucket["status"] == "abnormal"
    assert bucket["level"] == 2
    assert bucket["diagnosedCount"] == 2
    assert bucket["hasGap"] is True
    assert result["summary"]["missedCount"] == 1


def test_timeline_distinguishes_missed_waiting_and_no_data():
    hour = 3_600_000
    result = DeviceHealthArchiveService.build_timeline(
        records=[
            _record(1_000, DiagnosisRecordStatus.MISSED),
            _record(hour + 1_000, DiagnosisRecordStatus.WAITING),
        ],
        start_ms=0,
        end_ms=3 * hour,
        interval_ms=hour,
    )

    assert [bucket["status"] for bucket in result["buckets"]] == [
        "missed",
        "waiting",
        "no_data",
    ]


def test_timeline_uses_partial_final_bucket():
    hour = 3_600_000
    result = DeviceHealthArchiveService.build_timeline(
        records=[],
        start_ms=0,
        end_ms=hour + 1_000,
        interval_ms=hour,
    )

    assert result["range"]["bucketCount"] == 2
    assert result["buckets"][-1]["endAt"] == "1970-01-01T01:00:01Z"


def test_normalize_range_rejects_more_than_one_year():
    with pytest.raises(ValueError, match="cannot exceed"):
        DeviceHealthArchiveService.normalize_range(
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 7, 1, tzinfo=timezone.utc),
        )


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return self


class _FakeSession:
    def __init__(self, results):
        self._results = iter(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _RowsResult(next(self._results))


@pytest.mark.asyncio
async def test_get_timeline_filters_records_by_selected_location():
    location_id = uuid4()
    session = _FakeSession([[]])

    await DeviceHealthArchiveService.get_timeline(
        session=session,
        tenant_id=uuid4(),
        device_id=uuid4(),
        location_id=location_id,
        start_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
        interval_hours=1,
    )

    compiled = session.statements[0].compile()
    assert "diagnosis_record.location_id" in str(session.statements[0])
    assert location_id in compiled.params.values()


@pytest.mark.asyncio
async def test_get_device_points_combines_active_and_historical_locations():
    active_id = uuid4()
    binding_history_id = uuid4()
    diagnosis_history_id = uuid4()
    sensor_id = uuid4()
    session = _FakeSession(
        [
            [
                (active_id, "泵端", 1, sensor_id, "A26SH00001", "泵端传感器"),
                (binding_history_id, "电机端", 0, uuid4(), "A26SH00002", None),
            ],
            [(active_id, "泵端"), (diagnosis_history_id, None)],
        ]
    )

    points = await DeviceHealthArchiveService.get_device_points(
        session=session,
        tenant_id=uuid4(),
        device_id=uuid4(),
    )

    assert {point["id"] for point in points} == {
        str(active_id),
        str(binding_history_id),
        str(diagnosis_history_id),
    }
    assert next(point for point in points if point["id"] == str(active_id))["name"] == "泵端"
    assert next(point for point in points if point["id"] == str(active_id))["active"] is True
    assert next(point for point in points if point["id"] == str(active_id))["sensor"] == {
        "id": str(sensor_id),
        "sn": "A26SH00001",
        "description": "泵端传感器",
    }
    assert next(point for point in points if point["id"] == str(binding_history_id))[
        "name"
    ] == "电机端"
    assert next(point for point in points if point["id"] == str(binding_history_id))[
        "active"
    ] is False
    assert next(point for point in points if point["id"] == str(binding_history_id))[
        "sensor"
    ] is None
    assert next(point for point in points if point["id"] == str(diagnosis_history_id))[
        "name"
    ].startswith("历史测点 ")
    assert points[0]["id"] == str(active_id)

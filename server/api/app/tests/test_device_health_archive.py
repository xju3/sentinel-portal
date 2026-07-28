from datetime import datetime, timezone
from types import SimpleNamespace

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

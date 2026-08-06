import pytest

from app.preparation.ingestion import _notification_schema_fields
from pub.services.notification.notification_service import NotificationService


def test_v1_notification_schema_uses_top_level_overall_level():
    fields = _notification_schema_fields(1, 4, [])

    assert fields == {"overall_level": 4}


def test_v2_notification_schema_uses_faults_without_overall_level():
    faults = [
        {
            "diagnosis_item_id": "4c795680-4013-4c96-b937-52d39b2ac65a",
            "fault_type": "vibration",
            "fault_level": 4,
        }
    ]

    fields = _notification_schema_fields(2, 4, faults)

    assert fields == {"schema_version": 2, "faults": faults}
    assert "overall_level" not in fields

    event = NotificationService.parse_event(
        {
            "event_id": "526c8c90-8fa6-495a-9687-867a32888539",
            "diagnosis_id": "526c8c90-8fa6-495a-9687-867a32888539",
            "report_id": "ed528894-9c78-4dfb-b416-ad7aea1e9db4",
            "device_id": "d382b38d-3d8c-411b-9a5f-baed94fe444b",
            "sensor_sn": "26SH00001",
            "diagnosed_at": "2026-08-05T12:17:30.342354+00:00",
            **fields,
        }
    )
    assert event.expanded_faults()[0].fault_level == 4


def test_notification_schema_rejects_unsupported_version():
    with pytest.raises(
        ValueError,
        match="notification_event_schema_version must be 1 or 2",
    ):
        _notification_schema_fields(3, 4, [])

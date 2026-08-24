from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.preparation.ingestion import (
    _committed_fault_event,
    _notification_schema_fields,
)
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


@pytest.mark.asyncio
async def test_committed_fault_event_contains_every_persisted_fault():
    diagnosis_id = uuid4()
    report_id = uuid4()
    device_id = uuid4()
    diagnosis = SimpleNamespace(
        id=diagnosis_id,
        report_uuid=report_id,
        device_id=device_id,
        overall_level=3,
        diagnosed_at=datetime(2026, 8, 24, 10, 0, 0),
    )
    items = [
        SimpleNamespace(id=uuid4(), fault_type="vibration", level=3),
        SimpleNamespace(id=uuid4(), fault_type="bearing_bpfi", level=1),
    ]
    diagnosis_result = Mock()
    diagnosis_result.scalar_one_or_none.return_value = diagnosis
    item_result = Mock()
    item_result.scalars.return_value.all.return_value = items
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=[diagnosis_result, item_result])
    )
    source_record = SimpleNamespace(
        id=report_id,
        sensor_sn="26SH00001",
        device_category_id=None,
        process_device_id=None,
    )

    event = await _committed_fault_event(
        session,
        source_record,
        schema_version=2,
    )

    assert event is not None
    assert event["event_id"] == str(diagnosis_id)
    assert event["device_id"] == str(device_id)
    assert [fault["fault_type"] for fault in event["faults"]] == [
        "vibration",
        "bearing_bpfi",
    ]

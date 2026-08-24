from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from pub.models.diagnosis import DiagnosisRecordStatus
from pub.models.report import DiagnosisTriggerPayload

from app.preparation import ingestion


class FakeSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_publish_committed_fault_event_raises_when_broker_does_not_ack(monkeypatch):
    event = {"event_id": "event-1"}
    monkeypatch.setattr(ingestion, "publish_notification_event", AsyncMock(return_value=False))

    with pytest.raises(RuntimeError, match="event_id=event-1"):
        await ingestion._publish_committed_fault_event(event)


@pytest.mark.asyncio
async def test_dispatch_diagnosis_trigger_republishes_diagnosed_record_without_rerunning(monkeypatch):
    report = DiagnosisTriggerPayload(
        report_id=str(uuid4()),
        sensor_sn="SN-001",
        device_id=str(uuid4()),
        location_id=str(uuid4()),
        temperature_c=30.0,
        max_rms_vel=1.2,
        ts_ms=1780814415097,
        total=0,
    )
    source_record = SimpleNamespace(
        id=uuid4(),
        diagnosis_status=int(DiagnosisRecordStatus.DIAGNOSED),
        overall_level=3,
    )
    session = SimpleNamespace(get=AsyncMock(return_value=source_record))

    committed_event = {"event_id": "event-1"}
    build_event = AsyncMock(return_value=committed_event)
    republish = AsyncMock(return_value=None)
    context_lookup = AsyncMock(return_value={"unexpected": True})

    monkeypatch.setattr(ingestion, "_committed_fault_event", build_event)
    monkeypatch.setattr(ingestion, "_publish_committed_fault_event", republish)
    monkeypatch.setattr(ingestion, "publish_notification_event", AsyncMock(return_value=False))
    monkeypatch.setattr(
        "pub.manager.database.db_manager.SessionLocal",
        lambda: FakeSessionContext(session),
    )
    monkeypatch.setattr(
        "app.services.context.DeviceContextService.get_by_device_id_managed",
        context_lookup,
    )

    level = await ingestion.dispatch_diagnosis_trigger(report)

    assert level == 3
    build_event.assert_awaited_once()
    republish.assert_awaited_once_with(committed_event)
    context_lookup.assert_not_awaited()

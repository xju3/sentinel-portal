from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.routers import sensors


@pytest.mark.asyncio
async def test_receive_sensor_data_generates_ts_ms_when_device_omits_it(monkeypatch):
    dispatch = AsyncMock(return_value=[])
    monkeypatch.setattr(sensors, "dispatch_quick_diagnosis_tasks", dispatch)
    background_tasks = Mock()
    payload = {"sn": "STL26SH0001", "seq": 0, "sample_type": "normal"}

    response = await sensors.receive_sensor_data(
        background_tasks=background_tasks,
        payload=payload,
        session=Mock(),
    )

    assert response.code == 0
    assert "ts_ms" not in payload

    stored_payload = dispatch.await_args.kwargs["payload"]
    assert isinstance(stored_payload["ts_ms"], int)
    assert stored_payload["ts_ms"] > 0

    background_tasks.add_task.assert_called_once()
    task_args = background_tasks.add_task.call_args.args
    assert task_args[0] is sensors._process_sensor_data_background_async
    assert task_args[1].startswith("STL26SH0001/")
    assert task_args[2] is stored_payload
    assert task_args[3] == stored_payload["report_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("patrol_minutes", "seq", "expected_age"),
    [
        (60, 2, timedelta(hours=2)),
        (30, 4, timedelta(hours=2)),
    ],
)
async def test_receive_sensor_data_backdates_by_seq_and_patrol_frequency(
    monkeypatch,
    patrol_minutes,
    seq,
    expected_age,
):
    dispatch = AsyncMock(return_value=[])
    get_context = AsyncMock(
        return_value={"health_check": {"patrol": patrol_minutes}}
    )
    monkeypatch.setattr(sensors, "dispatch_quick_diagnosis_tasks", dispatch)
    monkeypatch.setattr(sensors.DiagnosisContextService, "get_by_sn", get_context)
    background_tasks = Mock()
    session = Mock()
    received_at = datetime.now(timezone.utc)

    await sensors.receive_sensor_data(
        background_tasks=background_tasks,
        payload={"sn": "STL26SH0001", "seq": seq},
        session=session,
    )

    stored_payload = dispatch.await_args.kwargs["payload"]
    sample_time = datetime.fromtimestamp(stored_payload["ts_ms"] / 1000, timezone.utc)
    assert abs((received_at - sample_time - expected_age).total_seconds()) < 1
    get_context.assert_awaited_once_with(session, "STL26SH0001")

    object_name = background_tasks.add_task.call_args.args[1]
    expected_path_time = sample_time.astimezone(timezone(timedelta(hours=8)))
    assert object_name == f"STL26SH0001/{expected_path_time.strftime('%Y/%m/%d/%H-%M-%S')}.json"


@pytest.mark.asyncio
async def test_receive_sensor_data_seq_zero_does_not_load_patrol_frequency(monkeypatch):
    dispatch = AsyncMock(return_value=[])
    get_context = AsyncMock()
    monkeypatch.setattr(sensors, "dispatch_quick_diagnosis_tasks", dispatch)
    monkeypatch.setattr(sensors.DiagnosisContextService, "get_by_sn", get_context)

    await sensors.receive_sensor_data(
        background_tasks=Mock(),
        payload={"sn": "STL26SH0001", "seq": 0},
        session=Mock(),
    )

    get_context.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("seq", [-1, 1.5, "2", True])
async def test_receive_sensor_data_rejects_invalid_seq(seq):
    with pytest.raises(HTTPException) as exc_info:
        await sensors.receive_sensor_data(
            background_tasks=Mock(),
            payload={"sn": "STL26SH0001", "seq": seq},
            session=Mock(),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_receive_sensor_data_rejects_missing_patrol_frequency(monkeypatch):
    monkeypatch.setattr(
        sensors.DiagnosisContextService,
        "get_by_sn",
        AsyncMock(return_value={"health_check": None}),
    )

    with pytest.raises(HTTPException) as exc_info:
        await sensors.receive_sensor_data(
            background_tasks=Mock(),
            payload={"sn": "STL26SH0001", "seq": 1},
            session=Mock(),
        )

    assert exc_info.value.status_code == 400
    assert "Patrol frequency is not configured" in exc_info.value.detail

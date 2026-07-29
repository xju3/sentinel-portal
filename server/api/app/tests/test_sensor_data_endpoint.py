from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.routers import sensors


@pytest.fixture(autouse=True)
def mock_sensor_metadata_cache(monkeypatch):
    redis_client = Mock()
    redis_client.get.return_value = None
    monkeypatch.setattr(
        sensors.redis_manager,
        "get_client",
        Mock(return_value=redis_client),
    )
    monkeypatch.setattr(
        sensors.SensorDbService,
        "get_sensor_metadata_for_cache",
        AsyncMock(return_value=None),
    )


@pytest.mark.asyncio
async def test_receive_sensor_data_generates_ts_ms_when_device_omits_it(monkeypatch):
    dispatch = AsyncMock(return_value=[])
    monkeypatch.setattr(sensors, "dispatch_quick_diagnosis_tasks", dispatch)
    background_tasks = Mock()
    payload = {
        "sn": "STL26SH0001",
        "delay": 0,
        "period": 1,
        "sample_type": "normal",
    }

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
    ("period", "delay", "expected_age"),
    [
        (1, 2, timedelta(minutes=2)),
        (0.5, 4, timedelta(minutes=2)),
    ],
)
async def test_receive_sensor_data_backdates_by_delay_and_payload_period(
    monkeypatch,
    period,
    delay,
    expected_age,
):
    dispatch = AsyncMock(return_value=[])
    monkeypatch.setattr(sensors, "dispatch_quick_diagnosis_tasks", dispatch)
    background_tasks = Mock()
    session = Mock()
    received_at = datetime.now(timezone.utc)

    await sensors.receive_sensor_data(
        background_tasks=background_tasks,
        payload={"sn": "STL26SH0001", "delay": delay, "period": period},
        session=session,
    )

    stored_payload = dispatch.await_args.kwargs["payload"]
    sample_time = datetime.fromtimestamp(stored_payload["ts_ms"] / 1000, timezone.utc)
    assert abs((received_at - sample_time - expected_age).total_seconds()) < 1

    object_name = background_tasks.add_task.call_args.args[1]
    expected_path_time = sample_time.astimezone(timezone(timedelta(hours=8)))
    assert object_name == f"STL26SH0001/{expected_path_time.strftime('%Y/%m/%d/%H-%M-%S')}.json"


@pytest.mark.asyncio
async def test_receive_sensor_data_current_sample_does_not_require_period(monkeypatch):
    dispatch = AsyncMock(return_value=[])
    monkeypatch.setattr(sensors, "dispatch_quick_diagnosis_tasks", dispatch)

    await sensors.receive_sensor_data(
        background_tasks=Mock(),
        payload={"sn": "STL26SH0001", "delay": 0},
        session=Mock(),
    )

    stored_payload = dispatch.await_args.kwargs["payload"]
    sample_time = datetime.fromtimestamp(stored_payload["ts_ms"] / 1000, timezone.utc)
    assert abs((datetime.now(timezone.utc) - sample_time).total_seconds()) < 1


@pytest.mark.asyncio
@pytest.mark.parametrize("delay", [-1, "2", True, float("nan")])
async def test_receive_sensor_data_rejects_invalid_delay(delay):
    with pytest.raises(HTTPException) as exc_info:
        await sensors.receive_sensor_data(
            background_tasks=Mock(),
            payload={"sn": "STL26SH0001", "delay": delay, "period": 1},
            session=Mock(),
        )

    assert exc_info.value.status_code == 400
    assert "'delay'" in exc_info.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize("period", [None, 0, -1, "1", True, float("nan")])
async def test_receive_sensor_data_rejects_invalid_period_for_backfill(period):
    with pytest.raises(HTTPException) as exc_info:
        await sensors.receive_sensor_data(
            background_tasks=Mock(),
            payload={"sn": "STL26SH0001", "delay": 1, "period": period},
            session=Mock(),
        )

    assert exc_info.value.status_code == 400
    assert "'period'" in exc_info.value.detail

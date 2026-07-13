from unittest.mock import AsyncMock, Mock

import pytest

from app.routers import sensors


@pytest.mark.asyncio
async def test_receive_sensor_data_generates_ts_ms_when_device_omits_it(monkeypatch):
    dispatch = AsyncMock(return_value=[])
    monkeypatch.setattr(sensors, "dispatch_quick_diagnosis_tasks", dispatch)
    background_tasks = Mock()
    payload = {"sn": "STL26SH0001", "sample_type": "normal"}

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

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers import sensors


@pytest.mark.asyncio
async def test_sensor_binding_returns_location_specific_bearing_orders(monkeypatch):
    device_id = uuid4()
    location_id = uuid4()
    binding_id = uuid4()
    bearing_id = uuid4()
    monkeypatch.setattr(
        sensors.SensorDbService,
        "get_binding_by_sn",
        AsyncMock(
            return_value={
                "device_id": device_id,
                "location_id": location_id,
                "rpm": 1500,
                "bearing": {
                    "binding_id": binding_id,
                    "bearing_id": bearing_id,
                    "brand": "SKF",
                    "model": "6205",
                    "bearing_type": "DEEP_GROOVE_BALL",
                    "shaft_speed_ratio": 0.2,
                    "shaft_rpm": 300,
                    "fault_orders": {
                        "bpfo": 3.2,
                        "bpfi": 4.8,
                        "bsf": 2.4,
                        "ftf": 0.4,
                    },
                },
            }
        ),
    )

    response = await sensors.get_sensor_binding(sn="SN-001", session=Mock())

    assert response.data["device_id"] == str(device_id)
    assert response.data["location_id"] == str(location_id)
    assert "location_id" not in response.data["bearing"]
    assert response.data["bearing"]["shaft_speed_ratio"] == 0.2
    assert response.data["bearing"]["shaft_rpm"] == 300
    assert response.data["bearing"]["fault_orders"]["bpfi"] == 4.8


@pytest.mark.asyncio
async def test_sensor_binding_query_matches_bearing_by_spec_and_location():
    device_id = uuid4()
    location_id = uuid4()
    bearing_id = uuid4()
    binding_id = uuid4()
    query_result = Mock()
    query_result.first.return_value = SimpleNamespace(
        device_inst_id=device_id,
        location_id=location_id,
        rpm=1500,
        binding_id=binding_id,
        bearing_id=bearing_id,
        shaft_speed_ratio=0.2,
        brand="SKF",
        model="6205",
        bearing_type="DEEP_GROOVE_BALL",
        rolling_element_count=8,
        rolling_element_diameter_mm=10,
        pitch_diameter_mm=50,
        contact_angle_deg=0,
    )
    session = Mock()
    session.execute = AsyncMock(return_value=query_result)

    binding = await sensors.SensorDbService.get_binding_by_sn(session, "SN-001")

    statement = str(session.execute.await_args.args[0])
    assert "device_spec_bearing.location_id = sensor_monitoring.location_id" in statement
    assert binding["location_id"] == location_id
    assert binding["bearing"]["shaft_rpm"] == 300
    assert binding["bearing"]["fault_orders"]["bpfo"] == pytest.approx(3.2)


@pytest.mark.asyncio
async def test_unbound_sensor_binding_query_removes_stale_metadata_cache(monkeypatch):
    redis_client = Mock()
    monkeypatch.setattr(
        sensors.SensorDbService,
        "get_binding_by_sn",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        sensors.SensorDbService,
        "get_sensor_metadata_for_cache",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        sensors.redis_manager,
        "get_client",
        Mock(return_value=redis_client),
    )

    response = await sensors.get_sensor_binding(sn="SN-UNBOUND", session=Mock())

    assert response.data["device_id"] is None
    assert response.data["location_id"] is None
    redis_client.delete.assert_called_once_with("sensor_meta:SN-UNBOUND")


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
async def test_receive_sensor_data_accepts_optional_bearing_features(monkeypatch):
    dispatch = AsyncMock(return_value=[])
    monkeypatch.setattr(sensors, "dispatch_quick_diagnosis_tasks", dispatch)
    bearing_features = {
        axis: {
            "status": 0,
            "envelope_kurtosis": 4.2,
            "fault_candidates": {},
        }
        for axis in ("X", "Y", "Z")
    }

    await sensors.receive_sensor_data(
        background_tasks=Mock(),
        payload={"sn": "STL26SH0001", "bearing_features": bearing_features},
        session=Mock(),
    )

    assert dispatch.await_args.kwargs["payload"]["bearing_features"] == bearing_features


@pytest.mark.asyncio
async def test_receive_sensor_data_rejects_invalid_bearing_features():
    with pytest.raises(HTTPException) as exc:
        await sensors.receive_sensor_data(
            background_tasks=Mock(),
            payload={
                "sn": "STL26SH0001",
                "bearing_features": {"X": {"status": 0}},
            },
            session=Mock(),
        )

    assert exc.value.status_code == 400
    assert "bearing_features" in exc.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("period", "delay", "expected_age"),
    [
        (20, 1200, timedelta(seconds=1200)),
        (0.5, 4, timedelta(seconds=4)),
    ],
)
async def test_receive_sensor_data_backdates_by_delay_seconds_independent_of_period(
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
async def test_delayed_report_uses_binding_valid_at_sample_time(monkeypatch):
    historical_device_id = str(uuid4())
    historical_location_id = str(uuid4())
    resolve_metadata = AsyncMock(
        return_value={
            "sensor_sn": "STL26SH0001",
            "device_id": historical_device_id,
            "location_id": historical_location_id,
        }
    )
    dispatch = AsyncMock(return_value=[])
    monkeypatch.setattr(
        sensors.SensorDbService,
        "get_sensor_metadata_for_cache",
        resolve_metadata,
    )
    monkeypatch.setattr(sensors, "dispatch_quick_diagnosis_tasks", dispatch)

    await sensors.receive_sensor_data(
        background_tasks=Mock(),
        payload={
            "sn": "STL26SH0001",
            "delay": 2,
            "period": 60,
            "device_id": str(uuid4()),
            "location_id": str(uuid4()),
        },
        session=Mock(),
    )

    stored_payload = dispatch.await_args.kwargs["payload"]
    assert stored_payload["device_id"] == historical_device_id
    assert stored_payload["location_id"] == historical_location_id
    resolve_metadata.assert_awaited_once_with(
        ANY,
        "STL26SH0001",
        sampled_at_ms=stored_payload["ts_ms"],
    )


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
async def test_receive_sensor_data_requires_task_decision_to_succeed(monkeypatch):
    monkeypatch.setattr(
        sensors,
        "dispatch_quick_diagnosis_tasks",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    background_tasks = Mock()

    with pytest.raises(HTTPException) as exc_info:
        await sensors.receive_sensor_data(
            background_tasks=background_tasks,
            payload={"sn": "STL26SH0001", "delay": 0},
            session=Mock(),
        )

    assert exc_info.value.status_code == 503
    background_tasks.add_task.assert_not_called()


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
async def test_receive_sensor_data_delayed_sample_does_not_require_period(monkeypatch):
    dispatch = AsyncMock(return_value=[])
    monkeypatch.setattr(sensors, "dispatch_quick_diagnosis_tasks", dispatch)

    await sensors.receive_sensor_data(
        background_tasks=Mock(),
        payload={"sn": "STL26SH0001", "delay": 1200},
        session=Mock(),
    )

    stored_payload = dispatch.await_args.kwargs["payload"]
    sample_time = datetime.fromtimestamp(stored_payload["ts_ms"] / 1000, timezone.utc)
    expected_age = timedelta(seconds=1200)
    assert abs((datetime.now(timezone.utc) - sample_time - expected_age).total_seconds()) < 1

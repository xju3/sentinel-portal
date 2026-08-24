import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from pub.services import build_quick_dispatch_plan
from pub.services.dispatch import quick_dispatch_service


def _payload(
    *,
    temperature_c=42.0,
    rms_z=2.0,
    task_id="",
    sample_type="normal",
    clipped=False,
    range_g=2,
    kurtosis=3.0,
):
    clip_count = 1 if clipped else 0
    clip_ratio = 0.01 if clipped else 0
    return {
        "sn": "STL26SH0001",
        "ts_ms": 1780814415097,
        "temperature_c": temperature_c,
        "requested_range_g": range_g,
        "range_g": range_g,
        "points": 4096,
        "fs_hz": 26667,
        "task_id": task_id,
        "sample_type": sample_type,
        "quality": {
            "status": "ok",
            "auto_range": False,
            "attempts": [
                {
                    "range_g": range_g,
                    "accepted": True,
                    "reason": "ok",
                    "clip_threshold_g": 1.96,
                    "axes": {
                        "X": {"max_abs_g": 0.2, "clip_count": 0, "clip_ratio": 0},
                        "Y": {"max_abs_g": 0.2, "clip_count": 0, "clip_ratio": 0},
                        "Z": {"max_abs_g": 1.96, "clip_count": clip_count, "clip_ratio": clip_ratio},
                    },
                }
            ],
        },
        "axis_features": {
            "X": {"time": {"rms_vel_mm_s": 1.0, "kurtosis": kurtosis}},
            "Y": {"time": {"rms_vel_mm_s": 1.2}},
            "Z": {"time": {"rms_vel_mm_s": rms_z}},
        },
    }


def _last_regular(*, temperature_c=40.0, rms_z=2.0):
    return {
        "report_id": "last",
        "sn": "STL26SH0001",
        "ts_ms": 1780810000000,
        "task_id": "",
        "sample_type": "normal",
        "temperature_c": temperature_c,
        "rms_vel_mm_s": {"X": 1.0, "Y": 1.2, "Z": rms_z},
    }


def _plan(payload, last_regular=None):
    return build_quick_dispatch_plan(
        report_id="r1",
        sn="STL26SH0001",
        payload=payload,
        last_regular=last_regular,
    )


def test_quick_dispatch_uses_vibration_only_for_resampling():
    plan = _plan(
        _payload(temperature_c=53.0, rms_z=7.9),
        _last_regular(temperature_c=45.0, rms_z=4.5),
    )

    assert plan.spec is not None
    assert plan.spec.action == 53
    assert plan.spec.val == 3
    assert any("RMS" in reason for reason in plan.reasons)
    assert not any("温度" in reason for reason in plan.reasons)


def test_quick_dispatch_does_not_resample_for_temperature_only():
    plan = _plan(
        _payload(temperature_c=53.0, rms_z=2.0),
        _last_regular(temperature_c=45.0, rms_z=2.0),
    )

    assert plan.spec is None
    assert plan.skipped_reason == "no quick trigger"


def test_quick_dispatch_resamples_for_early_bearing_kurtosis_with_normal_rms():
    plan = _plan(
        _payload(rms_z=2.0, kurtosis=4.8),
        _last_regular(rms_z=2.0),
    )

    assert plan.spec is not None
    assert plan.spec.action == 53
    assert plan.spec.val == 3
    assert any("峭度" in reason for reason in plan.reasons)


@pytest.mark.parametrize("range_g", [2, 8, 16])
def test_quick_dispatch_does_not_override_device_auto_range(range_g):
    plan = _plan(_payload(clipped=True, range_g=range_g), _last_regular())

    assert plan.spec is None
    assert plan.skipped_reason == "no quick trigger"


def test_quick_dispatch_skips_task_reports():
    plan = _plan(_payload(task_id="11111111-2222-3333-4444-555555555555"), _last_regular())

    assert plan.spec is None
    assert plan.skipped_reason == "task report"


def test_quick_dispatch_skips_non_normal_samples():
    plan = _plan(_payload(sample_type="debug", temperature_c=60.0, rms_z=8.0), _last_regular())

    assert plan.spec is None
    assert plan.skipped_reason == "sample_type=debug"


@pytest.mark.asyncio
async def test_regular_report_creates_due_daily_fft_before_dispatch(monkeypatch):
    ensure_daily = AsyncMock()
    dispatch = AsyncMock(return_value=[{"id": "fft", "action": 99, "val": 0}])
    monkeypatch.setattr(
        quick_dispatch_service,
        "get_last_regular_snapshot",
        lambda _sn: _last_regular(),
    )
    monkeypatch.setattr(quick_dispatch_service, "ensure_daily_fft_task", ensure_daily)
    monkeypatch.setattr(
        quick_dispatch_service,
        "dispatch_pending_sensor_tasks",
        dispatch,
    )

    tasks = await quick_dispatch_service.dispatch_quick_diagnosis_tasks(
        session=object(),
        report_id="r1",
        sn="STL26SH0001",
        payload=_payload(),
    )

    ensure_daily.assert_awaited_once()
    assert tasks == [{"id": "fft", "action": 99, "val": 0}]


@pytest.mark.asyncio
async def test_final_resampling_report_creates_fft_in_same_dispatch(monkeypatch):
    task = SimpleNamespace(
        id=uuid4(),
        task_purpose="RESAMPLING",
        val=3,
    )
    record_report = AsyncMock(return_value=task)
    followup_fft = SimpleNamespace(id=uuid4(), status=0)
    ensure_followup = AsyncMock(return_value=followup_fft)
    dispatch = AsyncMock(return_value=[{"id": "fft", "action": 99, "val": 0}])
    monkeypatch.setattr(
        quick_dispatch_service,
        "record_sensor_task_report",
        record_report,
    )
    monkeypatch.setattr(
        quick_dispatch_service,
        "ensure_resampling_followup_fft_task",
        ensure_followup,
    )
    monkeypatch.setattr(
        quick_dispatch_service,
        "dispatch_pending_sensor_tasks",
        dispatch,
    )
    monkeypatch.setattr(
        quick_dispatch_service,
        "get_last_regular_snapshot",
        lambda _sn: _last_regular(),
    )
    payload = _payload(
        task_id="11111111-2222-3333-4444-555555555555",
        kurtosis=5.2,
    )
    payload["task_sequence"] = 3

    tasks = await quick_dispatch_service.dispatch_quick_diagnosis_tasks(
        session=object(),
        report_id="r3",
        sn="STL26SH0001",
        payload=payload,
    )

    ensure_followup.assert_awaited_once()
    assert ensure_followup.await_args.kwargs["resampling_task_id"] == task.id
    assert tasks == [{"id": "fft", "action": 99, "val": 0}]


@pytest.mark.asyncio
async def test_missing_device_sequence_is_added_to_diagnosis_payload(monkeypatch):
    task = SimpleNamespace(
        id=uuid4(),
        task_purpose="RESAMPLING",
        val=3,
    )
    task_report = SimpleNamespace(sequence=2)
    payload = _payload(task_id=str(task.id))
    monkeypatch.setattr(
        quick_dispatch_service,
        "record_sensor_task_report",
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        quick_dispatch_service,
        "get_sensor_task_report_by_report_id",
        AsyncMock(return_value=task_report),
    )
    monkeypatch.setattr(
        quick_dispatch_service,
        "dispatch_pending_sensor_tasks",
        AsyncMock(return_value=[]),
    )

    await quick_dispatch_service.dispatch_quick_diagnosis_tasks(
        session=object(),
        report_id="report-2",
        sn="STL26SH0001",
        payload=payload,
    )

    assert payload["task_sequence"] == 2


@pytest.mark.asyncio
async def test_unrecorded_task_report_never_enters_diagnosis_pipeline(monkeypatch):
    task_id = str(uuid4())
    monkeypatch.setattr(
        quick_dispatch_service,
        "record_sensor_task_report",
        AsyncMock(return_value=None),
    )
    dispatch = AsyncMock(return_value=[])
    monkeypatch.setattr(
        quick_dispatch_service,
        "dispatch_pending_sensor_tasks",
        dispatch,
    )

    with pytest.raises(ValueError, match="could not be recorded"):
        await quick_dispatch_service.dispatch_quick_diagnosis_tasks(
            session=object(),
            report_id="report-invalid",
            sn="STL26SH0001",
            payload=_payload(task_id=task_id),
        )

    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_final_resampling_retry_returns_linked_dispatched_fft(monkeypatch):
    task = SimpleNamespace(id=uuid4(), task_purpose="RESAMPLING", val=3)
    fft_task = SimpleNamespace(id=uuid4(), status=2)
    monkeypatch.setattr(
        quick_dispatch_service,
        "record_sensor_task_report",
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        quick_dispatch_service,
        "ensure_resampling_followup_fft_task",
        AsyncMock(return_value=fft_task),
    )
    monkeypatch.setattr(
        quick_dispatch_service,
        "dispatch_pending_sensor_tasks",
        AsyncMock(return_value=[]),
    )
    serialize = AsyncMock(
        return_value={"id": str(fft_task.id), "action": 99, "val": 0}
    )
    monkeypatch.setattr(
        quick_dispatch_service,
        "sensor_task_to_device_payload",
        serialize,
    )
    monkeypatch.setattr(
        quick_dispatch_service,
        "get_last_regular_snapshot",
        lambda _sn: _last_regular(),
    )
    payload = _payload(
        task_id="11111111-2222-3333-4444-555555555555",
        kurtosis=5.2,
    )
    payload["task_sequence"] = 3

    tasks = await quick_dispatch_service.dispatch_quick_diagnosis_tasks(
        session=object(),
        report_id="r3-retry",
        sn="STL26SH0001",
        payload=payload,
    )

    assert tasks == [{"id": str(fft_task.id), "action": 99, "val": 0}]
    serialize.assert_awaited_once()


@pytest.mark.asyncio
async def test_resampling_report_before_final_sequence_does_not_create_fft(monkeypatch):
    task = SimpleNamespace(id=uuid4(), task_purpose="RESAMPLING", val=3)
    monkeypatch.setattr(
        quick_dispatch_service,
        "record_sensor_task_report",
        AsyncMock(return_value=task),
    )
    ensure_followup = AsyncMock()
    monkeypatch.setattr(
        quick_dispatch_service,
        "ensure_resampling_followup_fft_task",
        ensure_followup,
    )
    monkeypatch.setattr(
        quick_dispatch_service,
        "dispatch_pending_sensor_tasks",
        AsyncMock(return_value=[]),
    )
    payload = _payload(
        task_id="11111111-2222-3333-4444-555555555555",
        kurtosis=5.2,
    )
    payload["task_sequence"] = 2

    await quick_dispatch_service.dispatch_quick_diagnosis_tasks(
        session=object(),
        report_id="r2",
        sn="STL26SH0001",
        payload=payload,
    )

    ensure_followup.assert_not_awaited()


@pytest.mark.asyncio
async def test_final_resampling_report_confirmed_normal_does_not_create_fft(monkeypatch):
    task = SimpleNamespace(id=uuid4(), task_purpose="RESAMPLING", val=3)
    monkeypatch.setattr(
        quick_dispatch_service,
        "record_sensor_task_report",
        AsyncMock(return_value=task),
    )
    ensure_followup = AsyncMock()
    monkeypatch.setattr(
        quick_dispatch_service,
        "ensure_resampling_followup_fft_task",
        ensure_followup,
    )
    monkeypatch.setattr(
        quick_dispatch_service,
        "dispatch_pending_sensor_tasks",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        quick_dispatch_service,
        "get_last_regular_snapshot",
        lambda _sn: _last_regular(),
    )
    payload = _payload(
        task_id="11111111-2222-3333-4444-555555555555",
        rms_z=2.0,
        kurtosis=3.0,
    )
    payload["task_sequence"] = 3

    await quick_dispatch_service.dispatch_quick_diagnosis_tasks(
        session=object(),
        report_id="r3",
        sn="STL26SH0001",
        payload=payload,
    )

    ensure_followup.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_normal_report_does_not_schedule_daily_fft(monkeypatch):
    ensure_daily = AsyncMock()
    dispatch = AsyncMock(return_value=[])
    monkeypatch.setattr(
        quick_dispatch_service,
        "get_last_regular_snapshot",
        lambda _sn: _last_regular(),
    )
    monkeypatch.setattr(quick_dispatch_service, "ensure_daily_fft_task", ensure_daily)
    monkeypatch.setattr(
        quick_dispatch_service,
        "dispatch_pending_sensor_tasks",
        dispatch,
    )

    await quick_dispatch_service.dispatch_quick_diagnosis_tasks(
        session=object(),
        report_id="r1",
        sn="STL26SH0001",
        payload=_payload(sample_type="debug"),
    )

    ensure_daily.assert_not_awaited()

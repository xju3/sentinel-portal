import pytest

from pub.services import build_quick_dispatch_plan


def _payload(
    *,
    temperature_c=42.0,
    rms_z=2.0,
    task_id="",
    sample_type="normal",
    clipped=False,
    range_g=2,
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
            "X": {"time": {"rms_vel_mm_s": 1.0}},
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


def test_quick_dispatch_merges_temperature_and_rms_dense_collection():
    plan = _plan(
        _payload(temperature_c=53.0, rms_z=7.9),
        _last_regular(temperature_c=45.0, rms_z=4.5),
    )

    assert plan.spec is not None
    assert plan.spec.action == 15
    assert plan.spec.val == 3
    assert any("温度" in reason for reason in plan.reasons)
    assert any("RMS" in reason for reason in plan.reasons)


def test_quick_dispatch_uses_general_dense_action_for_temperature_only():
    plan = _plan(
        _payload(temperature_c=53.0, rms_z=2.0),
        _last_regular(temperature_c=45.0, rms_z=2.0),
    )

    assert plan.spec is not None
    assert plan.spec.action == 15
    assert plan.spec.val == 3


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

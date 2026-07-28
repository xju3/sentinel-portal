from pub.models.report import DiagnosisTriggerPayload

from app.preparation.ingestion import _advance_burst_state


def _report(
    report_id: str,
    *,
    delay: int,
    total: int,
    ts_ms: int,
) -> DiagnosisTriggerPayload:
    return DiagnosisTriggerPayload(
        report_id=report_id,
        sensor_sn="sensor-1",
        device_id="device-1",
        temperature_c=30.0,
        max_rms_vel=1.0,
        delay=delay,
        total=total,
        location_id="location-1",
        ts_ms=ts_ms,
    )


def test_no_delay_diagnoses_current_report_immediately():
    report = _report("current", delay=0, total=0, ts_ms=4_000)

    state, target = _advance_burst_state(None, report)

    assert state is None
    assert target == report


def test_complete_delayed_upload_diagnoses_original_current_report():
    candidate = _report("candidate", delay=0, total=3, ts_ms=4_000)
    delayed_1 = _report("delayed-1", delay=1, total=2, ts_ms=3_000)
    delayed_2 = _report("delayed-2", delay=2, total=1, ts_ms=2_000)
    delayed_3 = _report("delayed-3", delay=3, total=0, ts_ms=1_000)

    state, target = _advance_burst_state(None, candidate)
    assert target is None

    for report in (delayed_1, delayed_2):
        state, target = _advance_burst_state(state, report)
        assert target is None

    state, target = _advance_burst_state(state, delayed_3)

    assert state is None
    assert target == candidate


def test_missing_delayed_report_does_not_diagnose_even_when_total_zero_arrives():
    candidate = _report("candidate", delay=0, total=3, ts_ms=4_000)
    delayed_1 = _report("delayed-1", delay=1, total=2, ts_ms=3_000)
    delayed_3 = _report("delayed-3", delay=3, total=0, ts_ms=1_000)

    state, _ = _advance_burst_state(None, candidate)
    state, _ = _advance_burst_state(state, delayed_1)
    state, target = _advance_burst_state(state, delayed_3)

    assert state is not None
    assert target is None


def test_duplicate_delayed_report_does_not_count_twice():
    candidate = _report("candidate", delay=0, total=2, ts_ms=3_000)
    delayed = _report("delayed-1", delay=1, total=1, ts_ms=2_000)

    state, _ = _advance_burst_state(None, candidate)
    state, _ = _advance_burst_state(state, delayed)
    state, target = _advance_burst_state(state, delayed)

    assert state is not None
    assert target is None
    assert len(state["observations"]) == 1


def test_duplicate_candidate_does_not_discard_received_delayed_reports():
    candidate = _report("candidate", delay=0, total=2, ts_ms=3_000)
    delayed = _report("delayed-1", delay=1, total=1, ts_ms=2_000)

    state, _ = _advance_burst_state(None, candidate)
    state, _ = _advance_burst_state(state, delayed)
    state, target = _advance_burst_state(state, candidate)

    assert target is None
    assert state is not None
    assert set(state["observations"]) == {"delayed-1"}


def test_out_of_order_processing_waits_for_candidate_then_reconciles():
    delayed_1 = _report("delayed-1", delay=1, total=1, ts_ms=2_000)
    delayed_2 = _report("delayed-2", delay=2, total=0, ts_ms=1_000)
    candidate = _report("candidate", delay=0, total=2, ts_ms=3_000)

    state, _ = _advance_burst_state(None, delayed_1)
    state, _ = _advance_burst_state(state, delayed_2)
    state, target = _advance_burst_state(state, candidate)

    assert state is None
    assert target == candidate


def test_new_current_report_replaces_unfinished_candidate():
    old_candidate = _report("old", delay=0, total=2, ts_ms=3_000)
    old_delayed = _report("old-delayed", delay=1, total=1, ts_ms=2_000)
    new_candidate = _report("new", delay=0, total=1, ts_ms=5_000)

    state, _ = _advance_burst_state(None, old_candidate)
    state, _ = _advance_burst_state(state, old_delayed)
    state, target = _advance_burst_state(state, new_candidate)

    assert target is None
    assert state is not None
    assert state["candidate"]["report_id"] == "new"
    assert state["observations"] == {}

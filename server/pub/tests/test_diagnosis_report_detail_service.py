from types import SimpleNamespace
from uuid import uuid4

import pytest

from pub.services.diagnosis.diagnosis_report_detail_service import (
    DiagnosisReportBundle,
    DiagnosisReportDetailService,
)


@pytest.mark.asyncio
async def test_get_portal_detail_rejects_cross_tenant(monkeypatch):
    report_id = uuid4()
    report = SimpleNamespace(
        id=report_id,
        tenant_id=uuid4(),
        diagnosed_at=None,
        overall_level=3,
        diagnosis_status=2,
        ts_ms=1_721_110_000_000,
        sensor_sn="SN-1",
    )

    async def fake_load_bundle(*, session, report_id):
        return DiagnosisReportBundle(
            report=report,
            diagnosis=None,
            items=[],
            cases=[],
            attempts=[],
            temperature_trend=[],
            device=None,
            device_spec=None,
            device_category=None,
            process_device=None,
            process=None,
            location=None,
        )

    monkeypatch.setattr(
        DiagnosisReportDetailService,
        "_load_bundle",
        fake_load_bundle,
    )

    with pytest.raises(PermissionError):
        await DiagnosisReportDetailService.get_portal_detail(
            session=object(),
            report_id=report_id,
            tenant_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_get_report_detail_marks_legacy_partial_fault(monkeypatch):
    report_id = uuid4()
    report = SimpleNamespace(
        id=report_id,
        tenant_id=uuid4(),
        diagnosed_at=None,
        overall_level=2,
        diagnosis_status=2,
        ts_ms=1_721_110_000_000,
        sensor_sn="SN-2",
    )
    item = SimpleNamespace(
        id=uuid4(),
        metric_id=1,
        fault_type=None,
        level=2,
        description="RMS over baseline",
        evidence={"current": 4.2},
    )

    async def fake_load_bundle(*, session, report_id):
        return DiagnosisReportBundle(
            report=report,
            diagnosis=None,
            items=[item],
            cases=[],
            attempts=[],
            temperature_trend=[],
            device=None,
            device_spec=None,
            device_category=None,
            process_device=None,
            process=None,
            location=None,
        )

    monkeypatch.setattr(
        DiagnosisReportDetailService,
        "_load_bundle",
        fake_load_bundle,
    )

    payload = await DiagnosisReportDetailService.get_report_detail(
        session=object(),
        report_id=report_id,
    )

    assert payload["faults"][0]["fault_type"] == "vibration"
    assert payload["faults"][0]["trend"]["status"] == "legacy_partial"
    assert "fft" not in payload["faults"][0]

    filtered = await DiagnosisReportDetailService.get_report_detail(
        session=object(),
        report_id=report_id,
        fault_type="temperature",
    )
    assert filtered["faults"] == []
    assert filtered["report"]["overall_level"] is None
    assert filtered["provenance"]["thresholds"] == "legacy_partial"
    assert "fft_series" not in filtered["provenance"]

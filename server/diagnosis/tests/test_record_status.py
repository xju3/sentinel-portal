from pub.models.diagnosis import DiagnosisRecordStatus
from pub.services.diagnosis.diagnosis_record_service import (
    initial_diagnosis_status,
)


def test_current_report_without_backlog_starts_received():
    assert initial_diagnosis_status(0, 0) == DiagnosisRecordStatus.RECEIVED


def test_current_report_with_backlog_starts_waiting():
    assert initial_diagnosis_status(0, 3) == DiagnosisRecordStatus.WAITING


def test_delayed_report_is_skipped_as_diagnosis_target():
    assert initial_diagnosis_status(2, 1) == DiagnosisRecordStatus.SKIPPED

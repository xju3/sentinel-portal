from pub.models.diagnosis import (
    Diagnosis,
    DiagnosisCase,
    DiagnosisCaseAttempt,
    DiagnosisFft,
    DiagnosisItem,
    DiagnosisNotificationDelivery,
    DiagnosisNotificationOutbox,
    DiagnosisRecord,
)
from pub.models.sensor import SensorTask, SensorTaskReport


def _constraint_columns(table, name: str) -> list[str]:
    for constraint in table.constraints:
        if getattr(constraint, "name", None) == name:
            return [column.name for column in constraint.columns]
    raise AssertionError(f"Constraint {name} not found on {table.name}")


def _index_columns(table, name: str) -> list[str]:
    for index in table.indexes:
        if index.name == name:
            return [column.name for column in index.columns]
    raise AssertionError(f"Index {name} not found on {table.name}")


def _foreign_key_targets(table, column_name: str) -> set[str]:
    column = table.c[column_name]
    return {fk.target_fullname for fk in column.foreign_keys}


def test_diagnosis_models_keep_legacy_report_id_and_add_uuid_fk():
    assert "report_id" in Diagnosis.__table__.c
    assert "report_uuid" in Diagnosis.__table__.c
    assert _foreign_key_targets(Diagnosis.__table__, "report_uuid") == {
        "diagnosis_record.id"
    }
    assert "bearing_features" in DiagnosisRecord.__table__.c


def test_diagnosis_item_uses_explicit_fault_type():
    column = DiagnosisItem.__table__.c["fault_type"]
    assert str(column.type) == "VARCHAR(32)"
    assert column.nullable is True


def test_diagnosis_case_constraints_match_fault_scoped_investigation():
    assert _constraint_columns(
        DiagnosisCase.__table__,
        "uq_diagnosis_case_root_report_fault_type",
    ) == ["root_report_id", "fault_type"]
    assert _foreign_key_targets(DiagnosisCase.__table__, "root_report_id") == {
        "diagnosis_record.id"
    }


def test_diagnosis_case_attempt_constraints_match_report_and_sequence_identity():
    assert _constraint_columns(
        DiagnosisCaseAttempt.__table__,
        "uq_diagnosis_case_attempt_case_report",
    ) == ["case_id", "report_id"]
    assert _constraint_columns(
        DiagnosisCaseAttempt.__table__,
        "uq_diagnosis_case_attempt_case_phase_sequence",
    ) == ["case_id", "phase", "sequence"]
    assert _foreign_key_targets(DiagnosisCaseAttempt.__table__, "report_id") == {
        "diagnosis_record.id"
    }


def test_delivery_model_tracks_fault_dimensions_and_snapshot_recipient():
    table = DiagnosisNotificationDelivery.__table__
    assert _constraint_columns(
        table,
        "uq_diagnosis_notification_delivery_daily",
    ) == ["device_id", "fault_type", "fault_level", "employee_id", "notification_date"]
    assert "diagnosis_item_id" in table.c
    assert "fault_type" in table.c
    assert "fault_level" in table.c
    assert "recipient_wx_user_id" in table.c
    assert "attempt_count" in table.c
    assert "next_attempt_at" in table.c
    assert _index_columns(table, "idx_diagnosis_notification_report_fault") == [
        "report_id",
        "fault_type",
    ]
    assert _index_columns(table, "idx_diagnosis_notification_diagnosis_item") == [
        "diagnosis_item_id"
    ]
    assert _index_columns(table, "idx_diagnosis_notification_retry") == [
        "status",
        "next_attempt_at",
    ]


def test_outbox_model_uses_unique_event_id_and_report_fk():
    assert _constraint_columns(
        DiagnosisNotificationOutbox.__table__,
        "uq_diagnosis_notification_outbox_event",
    ) == ["event_id"]
    assert _foreign_key_targets(
        DiagnosisNotificationOutbox.__table__,
        "report_id",
    ) == {"diagnosis_record.id"}


def test_fft_diagnosis_is_idempotent_by_task_id():
    assert "report_id" not in DiagnosisFft.__table__.c
    assert "source_report_id" not in DiagnosisFft.__table__.c
    assert "source_diagnosis_id" not in DiagnosisFft.__table__.c
    assert "diagnosis_case_id" not in DiagnosisFft.__table__.c
    assert _constraint_columns(
        DiagnosisFft.__table__,
        "uq_diagnosis_fft_task_id",
    ) == ["fft_task_id"]


def test_sensor_task_models_add_case_and_report_uuid_links():
    assert _foreign_key_targets(SensorTask.__table__, "diagnosis_case_id") == {
        "diagnosis_case.id"
    }
    assert _foreign_key_targets(SensorTask.__table__, "source_report_id") == {
        "diagnosis_record.id"
    }
    assert _foreign_key_targets(SensorTaskReport.__table__, "report_uuid") == {
        "diagnosis_record.id"
    }

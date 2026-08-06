"""
Diagnosis result models.

Refactored for device-centric and integer-encoded diagnostic architecture.
"""

import uuid
from datetime import datetime
from enum import Enum, IntEnum

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Float,
    Uuid,
    BigInteger,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import relationship

from pub.models import Base


class DiagnosisRecordStatus(IntEnum):
    RECEIVED = 0
    WAITING = 1
    DIAGNOSED = 2
    SKIPPED = 3
    MISSED = 4


class DiagnosisNotificationDeliveryStatus(IntEnum):
    PENDING = 0
    SENDING = 1
    SENT = 2
    FAILED = 3


class DiagnosisFaultType(str, Enum):
    TEMPERATURE = "temperature"
    VIBRATION = "vibration"
    BEARING_BPFO = "bearing_bpfo"
    BEARING_BPFI = "bearing_bpfi"
    BEARING_BSF = "bearing_bsf"
    BEARING_FTF = "bearing_ftf"
    LEGACY = "legacy_aggregate"


class DiagnosisConfirmationStatus(str, Enum):
    INITIAL_ABNORMAL = "INITIAL_ABNORMAL"
    RESAMPLING = "RESAMPLING"
    RESOLVED_NORMAL = "RESOLVED_NORMAL"
    CONFIRMED_ABNORMAL = "CONFIRMED_ABNORMAL"


class DiagnosisCaseAttemptPhase(str, Enum):
    INITIAL = "INITIAL"
    RESAMPLE = "RESAMPLE"


class DiagnosisCaseAttemptResultStatus(str, Enum):
    NORMAL = "NORMAL"
    ABNORMAL = "ABNORMAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class DiagnosisNotificationOutboxStatus(str, Enum):
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class DiagnosisRecord(Base):
    """
    Metadata record for the raw incoming diagnostic JSON report.
    This tracks the payload's summary info independently of the algorithm results.
    """
    __tablename__ = "diagnosis_record"
    __table_args__ = (
        Index(
            "idx_diagnosis_record_device_health_time",
            "device_id",
            "diagnosis_status",
            "ts_ms",
        ),
        Index(
            "idx_diagnosis_record_tenant_health_time",
            "tenant_id",
            "diagnosis_status",
            "ts_ms",
        ),
        Index(
            "idx_diag_record_device_location_health_time",
            "device_id",
            "location_id",
            "ts_ms",
            "diagnosis_status",
        ),
    )
    
    # Matching data.json top-level fields
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    schema_version = Column(Integer, nullable=True)
    sensor_sn = Column(String(255), nullable=False, index=True)
    device_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    temperature_c = Column(Float, nullable=True)
    fs_hz = Column(Integer, nullable=True)
    requested_range_g = Column(Integer, nullable=True)
    range_g = Column(Integer, nullable=True)
    points = Column(Integer, nullable=True)
    task_id = Column(String(128), nullable=True)
    sample_type = Column(String(64), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    
    quality = Column(MySQLJSON, nullable=True, comment="Raw quality object")
    bearing_features = Column(
        MySQLJSON,
        nullable=True,
        comment="Device-computed per-axis bearing envelope evidence",
    )
    
    delay = Column(Integer, nullable=True, default=0)
    total = Column(Integer, nullable=True, default=0)
    diagnosis_status = Column(
        TINYINT(unsigned=True),
        nullable=False,
        default=DiagnosisRecordStatus.RECEIVED,
        comment="0=RECEIVED,1=WAITING,2=DIAGNOSED,3=SKIPPED,4=MISSED",
    )
    overall_level = Column(
        TINYINT(unsigned=True),
        nullable=True,
        comment="0=正常,1=关注,2=异常,3=告警,4=严重;NULL=未形成诊断",
    )
    diagnosed_at = Column(
        DateTime,
        nullable=True,
        comment="实际完成诊断的UTC时间",
    )
    
    sensor_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    location_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    tenant_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    region_id = Column(String(64), nullable=True, index=True)
    device_category_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    process_device_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    
    rpm = Column(Float, nullable=True)
    ts_ms = Column(BigInteger, nullable=False, index=True)
    
    # System fields
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

class Diagnosis(Base):
    """
    Main diagnosis record. 
    Anchors the diagnosis to the physical topology (device_id + location_id).
    """

    __tablename__ = "diagnosis"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    device_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    location_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    
    # Link to the original payload ID (e.g. MinIO object or MySQL raw record)
    report_id = Column(String(128), nullable=True, index=True)
    report_uuid = Column(
        Uuid(as_uuid=True),
        ForeignKey("diagnosis_record.id"),
        nullable=True,
        index=True,
    )
    
    # MAX of all item levels (0: Normal, 1: Attention, 2: Abnormal, 3: Warning, 4: Critical)
    overall_level = Column(Integer, nullable=False, default=0, index=True)
    
    # 0 for final confirmation, 1 for intermediate resampling records
    resampling = Column(TINYINT(1), nullable=False, default=0, index=True, comment="是否处于复采确认中")
    ds = Column(String(64), nullable=True, comment="数据来源: 常规检查/异常唤醒/复采任务(X/Y)")
    
    diagnosed_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    items = relationship(
        "DiagnosisItem",
        back_populates="diagnosis",
        cascade="all, delete-orphan",
    )

class DiagnosisItem(Base):
    """
    Specific metric check result for a diagnosis.
    """

    __tablename__ = "diagnosis_item"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    diagnosis_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("diagnosis.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # 0: Temperature, 1: Vib-X, 2: Vib-Y, 3: Vib-Z
    metric_id = Column(Integer, nullable=False, index=True)
    fault_type = Column(
        String(32),
        nullable=True,
        index=True,
        comment="temperature|vibration|legacy_aggregate",
    )
    
    # 0: Normal, 1: Attention, 2: Abnormal, 3: Warning, 4: Critical
    level = Column(Integer, nullable=False, default=0, index=True)
    
    # 0 for final confirmation, 1 for intermediate resampling records
    resampling = Column(TINYINT(1), nullable=False, default=0, index=True, comment="是否处于复采确认中")
    
    # Human readable fault description
    description = Column(String(255), nullable=True)
    
    # JSON payload for UI tooltips and algorithm debugging (e.g. ratio, effective_rise)
    evidence = Column(MySQLJSON, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    diagnosis = relationship("Diagnosis", back_populates="items")


class DiagnosisCase(Base):
    """Fault-specific investigation state anchored to one root diagnosis report."""

    __tablename__ = "diagnosis_case"
    __table_args__ = (
        UniqueConstraint(
            "root_report_id",
            "fault_type",
            name="uq_diagnosis_case_root_report_fault_type",
        ),
        Index(
            "idx_diagnosis_case_confirmation_status",
            "confirmation_status",
            "updated_at",
        ),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    root_report_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("diagnosis_record.id"),
        nullable=False,
        index=True,
    )
    device_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    sensor_sn = Column(String(255), nullable=False, index=True)
    fault_type = Column(String(32), nullable=False, index=True)
    confirmation_status = Column(
        String(32),
        nullable=False,
        default=DiagnosisConfirmationStatus.INITIAL_ABNORMAL.value,
        comment="INITIAL_ABNORMAL|RESAMPLING|RESOLVED_NORMAL|CONFIRMED_ABNORMAL",
    )
    resampling_task_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("sensor_task.id"),
        nullable=True,
        index=True,
    )
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    attempts = relationship(
        "DiagnosisCaseAttempt",
        back_populates="case",
        cascade="all, delete-orphan",
    )


class DiagnosisCaseAttempt(Base):
    """One diagnosis attempt within a fault-specific investigation case."""

    __tablename__ = "diagnosis_case_attempt"
    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "report_id",
            name="uq_diagnosis_case_attempt_case_report",
        ),
        UniqueConstraint(
            "case_id",
            "phase",
            "sequence",
            name="uq_diagnosis_case_attempt_case_phase_sequence",
        ),
        Index("idx_diagnosis_case_attempt_diagnosis_id", "diagnosis_id"),
        Index("idx_diagnosis_case_attempt_diagnosis_item_id", "diagnosis_item_id"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    case_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("diagnosis_case.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("diagnosis_record.id"),
        nullable=False,
        index=True,
    )
    diagnosis_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("diagnosis.id"),
        nullable=True,
        index=True,
    )
    diagnosis_item_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("diagnosis_item.id"),
        nullable=True,
        index=True,
    )
    phase = Column(
        String(16),
        nullable=False,
        comment="INITIAL|RESAMPLE",
    )
    sequence = Column(Integer, nullable=False)
    result_status = Column(
        String(32),
        nullable=False,
        comment="NORMAL|ABNORMAL|INSUFFICIENT_DATA",
    )
    fault_level = Column(
        TINYINT(unsigned=True),
        nullable=True,
        comment="0=正常,1=关注,2=异常,3=告警,4=严重",
    )
    description = Column(String(255), nullable=True)
    evidence = Column(MySQLJSON, nullable=True)
    diagnosed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    case = relationship("DiagnosisCase", back_populates="attempts")

class DiagnosisFft(Base):
    """
    Standalone FFT diagnosis result, identified by its action=99 task.
    """

    __tablename__ = "diagnosis_fft"
    __table_args__ = (
        UniqueConstraint(
            "fft_task_id",
            name="uq_diagnosis_fft_task_id",
        ),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # The SensorTask (action=99) that generated the FFT data
    fft_task_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    device_fft_record_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("device_fft_record.id"),
        nullable=True,
        index=True,
    )
    
    # Physical fault code or conclusion string (e.g. "UB", "BPFO")
    conclusion = Column(String(255), nullable=True)
    
    # Confidence level 0.0 ~ 1.0 to handle algorithmic uncertainty
    confidence = Column(Float, nullable=True)
    rpm_snapshot = Column(Float, nullable=True)
    base_frequency_hz = Column(Float, nullable=True)
    rpm_source = Column(String(32), nullable=True)
    spectrum_preview_object_key = Column(String(255), nullable=True)
    
    # Detailed evidence (e.g. matched frequencies, amplitudes)
    details = Column(MySQLJSON, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class DiagnosisNotificationDelivery(Base):
    """Daily WeChat delivery ledger for diagnosis notification events."""

    __tablename__ = "notification_delivery"
    __table_args__ = (
        UniqueConstraint(
            "device_id",
            "fault_type",
            "fault_level",
            "employee_id",
            "notification_date",
            name="uq_diagnosis_notification_delivery_daily",
        ),
        Index("idx_diagnosis_notification_event", "event_id"),
        Index("idx_diagnosis_notification_employee_status", "employee_id", "status"),
        Index("idx_diagnosis_notification_date_status", "notification_date", "status"),
        Index("idx_diagnosis_notification_report_fault", "report_id", "fault_type"),
        Index("idx_diagnosis_notification_diagnosis_item", "diagnosis_item_id"),
        Index("idx_diagnosis_notification_retry", "status", "next_attempt_at"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    event_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    diagnosis_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    report_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("diagnosis_record.id"),
        nullable=True,
        index=True,
    )
    device_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    diagnosis_item_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("diagnosis_item.id"),
        nullable=True,
        index=True,
    )
    sensor_sn = Column(String(255), nullable=True, index=True)
    device_category_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    process_device_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    overall_level = Column(
        TINYINT(unsigned=True),
        nullable=True,
        comment="1=关注,2=异常,3=告警,4=严重",
    )
    fault_type = Column(
        String(32),
        nullable=True,
        index=True,
        comment="temperature|vibration|legacy_aggregate",
    )
    fault_level = Column(
        TINYINT(unsigned=True),
        nullable=True,
        index=True,
        comment="1=关注,2=异常,3=告警,4=严重",
    )
    employee_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    wx_user_id = Column(String(255), nullable=False)
    recipient_wx_user_id = Column(String(255), nullable=True)
    notification_date = Column(Date, nullable=False, index=True)
    diagnosed_at = Column(
        DateTime,
        nullable=False,
        comment="诊断完成时间(UTC)",
    )
    status = Column(
        TINYINT(unsigned=True),
        nullable=False,
        default=DiagnosisNotificationDeliveryStatus.PENDING,
        comment="0=PENDING,1=SENDING,2=SENT,3=FAILED",
    )
    sent_at = Column(DateTime, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime, nullable=True)
    last_error = Column(String(1024), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class DiagnosisNotificationOutbox(Base):
    """Reliable handoff ledger between diagnosis commits and MQTT publishing."""

    __tablename__ = "notification_outbox"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_diagnosis_notification_outbox_event"),
        Index(
            "idx_diagnosis_notification_outbox_status_retry",
            "status",
            "next_attempt_at",
        ),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    event_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    diagnosis_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("diagnosis.id"),
        nullable=False,
        index=True,
    )
    report_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("diagnosis_record.id"),
        nullable=False,
        index=True,
    )
    payload = Column(MySQLJSON, nullable=False)
    status = Column(
        String(16),
        nullable=False,
        default=DiagnosisNotificationOutboxStatus.PENDING.value,
        comment="PENDING|PUBLISHED|FAILED",
    )
    attempt_count = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)
    last_error = Column(String(1024), nullable=True)

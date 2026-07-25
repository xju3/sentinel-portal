"""
Diagnosis result models.

Refactored for device-centric and integer-encoded diagnostic architecture.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Float,
    Uuid,
)
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import relationship

from pub.models import Base


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
    
    # MAX of all item levels (0: Normal, 1: Attention, 2: Abnormal, 3: Warning, 4: Critical)
    overall_level = Column(Integer, nullable=False, default=0, index=True)
    
    # 0 for final confirmation, 1 for intermediate resampling records
    resampling = Column(TINYINT(1), nullable=False, default=0, index=True, comment="是否处于复采确认中")
    
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


class DiagnosisFft(Base):
    """
    Independent table for FFT analysis conclusions.
    Linked to the final resampling action that triggered the FFT.
    """

    __tablename__ = "diagnosis_fft"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Links to the Diagnosis/report_id of the final resampling task that confirmed the anomaly
    report_id = Column(String(128), nullable=False, index=True)
    
    # The SensorTask (action=9xx) that generated the FFT data
    fft_task_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    
    # Physical fault code or conclusion string (e.g. "UB", "BPFO")
    conclusion = Column(String(255), nullable=True)
    
    # Confidence level 0.0 ~ 1.0 to handle algorithmic uncertainty
    confidence = Column(Float, nullable=True)
    
    # Detailed evidence (e.g. matched frequencies, amplitudes)
    details = Column(MySQLJSON, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

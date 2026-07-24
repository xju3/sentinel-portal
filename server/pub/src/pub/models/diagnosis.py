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
    Uuid,
)
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
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
    
    # Human readable fault description
    description = Column(String(255), nullable=True)
    
    # JSON payload for UI tooltips and algorithm debugging (e.g. ratio, effective_rise)
    evidence = Column(MySQLJSON, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    diagnosis = relationship("Diagnosis", back_populates="items")

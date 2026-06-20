"""
Diagnosis result models.

`DiagnosisResult` stores one complete diagnosis run for a sensor report.
`DiagnosisResultItem` stores the per-check conclusions and evidence that
explain the overall result.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
from sqlalchemy.orm import relationship

from pub.models import Base


class DiagnosisResult(Base):
    """Top-level diagnosis result for one sensor report and metric."""

    __tablename__ = "diagnosis_result"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    report_id = Column(String(128), nullable=False, index=True)
    sn = Column(String(255), nullable=False, index=True)
    sensor_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    sensor_monitoring_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    device_inst_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    device_spec_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    device_category_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    metric = Column(String(64), nullable=False, index=True)
    level = Column(String(32), nullable=False, index=True, comment="正常/关注/警告/严重")
    triggered = Column(Boolean, nullable=False, default=False, index=True)
    conclusion = Column(Text, nullable=False)
    evidence = Column(MySQLJSON, nullable=True, comment="Overall evidence list for the diagnosis")
    report_ts = Column(BigInteger, nullable=True, index=True, comment="Source report timestamp in Unix ms")
    diagnosed_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = relationship(
        "DiagnosisResultItem",
        back_populates="result",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DiagnosisResultItem.sort_order",
    )


class DiagnosisResultItem(Base):
    """Per-check diagnosis conclusion and evidence."""

    __tablename__ = "diagnosis_result_item"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    result_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("diagnosis_result.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort_order = Column(Integer, nullable=False, default=0)
    name = Column(String(64), nullable=False, index=True)
    level = Column(String(32), nullable=False, index=True, comment="未检测/正常/关注/警告/严重")
    triggered = Column(Boolean, nullable=False, default=False, index=True)
    conclusion = Column(Text, nullable=False)
    evidence = Column(MySQLJSON, nullable=True, comment="Evidence list or structured evidence object")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    result = relationship("DiagnosisResult", back_populates="items")

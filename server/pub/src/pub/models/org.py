"""
Organization Management Models (Department, Employee)
"""

import uuid
from sqlalchemy import (
    Column,
    String,
    Uuid,
    Boolean,
    ForeignKey,
    Table
)
from sqlalchemy.orm import relationship

from pub.models import Base

class EmployeeDepartment(Base):
    """Many-to-many relationship between Employee and Department"""
    __tablename__ = "employee_department"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    employee_id = Column(Uuid(as_uuid=True), ForeignKey("employee.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(Uuid(as_uuid=True), ForeignKey("department.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(Uuid(as_uuid=True), nullable=False, index=True)

class Department(Base):
    """Department entity model"""
    __tablename__ = "department"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(32), nullable=False, index=True)
    name = Column(String(64), nullable=False)
    description = Column(String(255))
    leader_id = Column(Uuid(as_uuid=True), ForeignKey("employee.id", ondelete="SET NULL"), nullable=True)
    parent_id = Column(Uuid(as_uuid=True), ForeignKey("department.id", ondelete="CASCADE"), nullable=True, index=True)
    tenant_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    active = Column(Boolean, default=True)

    # Relationships
    leader = relationship("Employee", foreign_keys=[leader_id])
    parent = relationship("Department", remote_side=[id], backref="children")
    employees = relationship("Employee", secondary="employee_department", back_populates="departments")

class Employee(Base):
    """Employee entity model"""
    __tablename__ = "employee"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(32), nullable=False, index=True)
    name = Column(String(64), nullable=False)
    mobile = Column(String(20), nullable=True)
    tenant_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    active = Column(Boolean, default=True)

    # Relationships
    departments = relationship("Department", secondary="employee_department", back_populates="employees")

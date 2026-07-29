"""
Device data models
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import relationship

from pub.models import Base

from pub.models.customer import IsoStandard, HealthCheckFreq, Supplier, Area

class DeviceCategoryEmployee(Base):
    """Many-to-many relationship between DeviceCategory and Employee"""
    __tablename__ = "device_category_employee"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    device_category_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    employee_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    trans_date = Column(DateTime, default=datetime.utcnow)
    status = Column(Boolean, default=True)

class ProcessDeviceEmployee(Base):
    """Many-to-many relationship between ProcessDevice and Employee for alarms"""
    __tablename__ = "process_device_employee"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    process_device_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    employee_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    trans_date = Column(DateTime, default=datetime.utcnow)
    status = Column(Boolean, default=True)

class DeviceCategory(Base):
    """Device category entity model"""

    __tablename__ = "device_category"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(64), nullable=False, unique=True)
    description = Column(String(255))
    parent_id = Column(Uuid(as_uuid=True), nullable=True, index=True)  # Self-referential link for category hierarchy
    vib_threshold_id = Column(Uuid(as_uuid=True), nullable=True, index=True)  # Optional link to vibration threshold for default values
    temp_threshold_id = Column(Uuid(as_uuid=True), nullable=True, index=True)  # Optional link to temperature threshold for default values
    health_check_freq_id  = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to health_check_freq for default frequencies
    tenant_id = Column(Uuid(as_uuid=True), default=uuid.uuid4, index=False) # link to tenant for multi-tenant support
    iso_standard_id = Column(Uuid(as_uuid=True), nullable=True, index=True)  # Optional link to ISO standard for compliance reference

    parent = relationship("DeviceCategory", primaryjoin="foreign(DeviceCategory.parent_id) == remote(DeviceCategory.id)", lazy="selectin", uselist=False)
    vib_threshold = relationship("SensorThreshold", primaryjoin="foreign(DeviceCategory.vib_threshold_id) == SensorThreshold.id", lazy="selectin", uselist=False)
    temp_threshold = relationship("SensorThreshold", primaryjoin="foreign(DeviceCategory.temp_threshold_id) == SensorThreshold.id", lazy="selectin", uselist=False)
    health_check_freq = relationship("HealthCheckFreq", primaryjoin="foreign(DeviceCategory.health_check_freq_id) == HealthCheckFreq.id", lazy="selectin", uselist=False)
    iso_standard = relationship("IsoStandard", primaryjoin="foreign(DeviceCategory.iso_standard_id) == IsoStandard.id", lazy="selectin", uselist=False)
    employees = relationship(
        "Employee",
        secondary="device_category_employee",
        primaryjoin="foreign(DeviceCategoryEmployee.device_category_id) == DeviceCategory.id",
        secondaryjoin="foreign(DeviceCategoryEmployee.employee_id) == Employee.id",
        backref="device_categories"
    )

class DeviceSpec(Base):
    """Device specification entity model"""

    __tablename__ = "device_spec"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(64), nullable=False)
    model = Column(String(32), nullable=False)
    description = Column(String(255))
    brand = Column(String(64), nullable=False)
    voltage = Column(Float, nullable=False, default=0.0)
    rpm = Column(Integer, nullable=False, default=0)
    supplier_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to supplier for multi-tenant support
    device_category_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to device_category

    supplier = relationship("Supplier", primaryjoin="foreign(DeviceSpec.supplier_id) == Supplier.id", lazy="selectin", uselist=False)
    device_category = relationship("DeviceCategory", primaryjoin="foreign(DeviceSpec.device_category_id) == DeviceCategory.id", lazy="selectin", uselist=False)


    def __repr__(self):
        return f"<DeviceSpec {self.id}: {self.name} - {self.model}>"

class DeviceInst(Base):
    """Device instance entity model"""

    __tablename__ = "device_inst"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(128), nullable=False, unique=True, index=True) # unique code for device instance, e.g. for QR code generation
    code = Column(String(64), nullable=False, unique=True, index=True)  # serial number for physical tracking
    purchase_date = Column(Date, nullable=True) # optional purchase date for lifecycle management
    life_span = Column(Integer, nullable=False, default=0)  # Expected lifespan in months
    desc = Column(String(128), nullable=True) # optional notes for device instance
    status = Column(SmallInteger, default=1, comment="tiny(1) status")
    active = Column(SmallInteger, default=1, comment="设备是否运行")
    available = Column(SmallInteger, default=1, comment="设备是否可用, 如未分配或正在维修则不可用")
    device_spec_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to device_specs

    device_spec = relationship(
        "DeviceSpec",
        primaryjoin="foreign(DeviceInst.device_spec_id) == DeviceSpec.id",
        lazy="selectin",
        uselist=False
    )

    sensor_monitorings = relationship(
        "SensorMonitoring",
        primaryjoin="DeviceInst.id == foreign(SensorMonitoring.device_inst_id)",
        lazy="selectin",
        uselist=True
    )

class Process(Base):
    """Device combo specification entity model"""

    __tablename__ = "process"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_process_tenant_code"),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), nullable=False, default=uuid.uuid4)
    code = Column(String(8), nullable=False)
    name = Column(String(64), nullable=False)

    status = Column(SmallInteger, default=1, comment="tiny(1) status")

class ProcessItem(Base):
    """Process item entity model"""

    __tablename__ = "process_item"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    process_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to processes
    device_spec_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    qty = Column(Integer, nullable=False, default=1)

    device_spec = relationship("DeviceSpec", primaryjoin="foreign(ProcessItem.device_spec_id) == DeviceSpec.id", lazy="selectin", uselist=False)

class ProcessDevice(Base):
    """Process device entity model"""

    __tablename__ = "process_device"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(8), nullable=False, unique=True, index=True)
    process_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to processes
    sn = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(SmallInteger, default=1, comment="tiny(1) status")
    area_id = Column(Uuid(as_uuid=True), nullable=True, index=True)  # Optional link to area for location-based processes

    process = relationship("Process", primaryjoin="foreign(ProcessDevice.process_id) == Process.id", lazy="selectin", uselist=False)
    area = relationship("Area", primaryjoin="foreign(ProcessDevice.area_id) == Area.id", lazy="selectin", uselist=False)
    employees = relationship(
        "Employee",
        secondary="process_device_employee",
        primaryjoin="foreign(ProcessDeviceEmployee.process_device_id) == ProcessDevice.id",
        secondaryjoin="foreign(ProcessDeviceEmployee.employee_id) == Employee.id",
        backref="process_devices"
    )

    def __repr__(self):
        return f"<ProcessDevice {self.id}: {self.code} - {self.sn}>"

class ProcessDeviceItem(Base):
    """Device combo instance detail entity model"""

    __tablename__ = "process_device_item"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(16), nullable=False, unique=True, index=True)
    desc = Column(String(128), nullable=False)
    device_inst_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to device_insts
    process_device_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to process_devices

    device_inst = relationship("DeviceInst", primaryjoin="foreign(ProcessDeviceItem.device_inst_id) == DeviceInst.id", lazy="selectin", uselist=False)

class DeviceBaseline(Base):
    """
    Dynamic health baseline for the device to track degradation over time.
    Calculated periodically (e.g. 7-day median) and used for relative thresholding.
    """

    __tablename__ = "device_baseline"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    device_inst_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # physical device instance
    metric_name = Column(String(64), nullable=False, index=True)  # e.g., 'vibration_rms'
    baseline_value = Column(Float, nullable=False, default=0.0)
    
    # Lifecycle tracking for historical tracing
    effective_from = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    effective_to = Column(DateTime, nullable=True, index=True)  # NULL means currently active
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    device_inst = relationship(
        "DeviceInst",
        primaryjoin="foreign(DeviceBaseline.device_inst_id) == DeviceInst.id",
        lazy="selectin",
        uselist=False
    )

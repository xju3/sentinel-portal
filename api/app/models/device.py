"""
Device data models
"""

import uuid
from sqlalchemy import Column, String, Date, Uuid, Integer, SmallInteger, Float, Boolean, Text

from app.models import Base

class IsoStandard(Base):
    """ISO standard entity model"""

    __tablename__ = "iso_standard"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(16), nullable=False, unique=True, index=True)
    name = Column(String(64), nullable=False)
    category = Column(String(32), nullable=False)
    foundation = Column(String(64), nullable=False)
    description = Column(String(255))

class DeviceCategory(Base):
    """Device category entity model"""

    __tablename__ = "device_category"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(64), nullable=False, unique=True)
    description = Column(String(255))
    parent_id = Column(Uuid(as_uuid=True), nullable=True, index=True)  # Self-referential link for category hierarchy
    health_check_freq_id  = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to health_check_freq for default frequencies
    tenant_id = Column(Uuid(as_uuid=True), default=uuid.uuid4, index=False) # link to tenant for multi-tenant support
    iso_standard_id = Column(Uuid(as_uuid=True), nullable=True, index=True)  # Optional link to ISO standard for compliance reference

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
    

    def __repr__(self):
        return f"<DeviceSpec {self.id}: {self.name} - {self.model}>"


class DeviceInst(Base):
    """Device instance entity model"""

    __tablename__ = "device_inst"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(16), nullable=False, unique=True, index=True) # unique code for device instance, e.g. for QR code generation
    sn = Column(String(64), nullable=False, unique=True, index=True)  # serial number for physical tracking
    purchase_date = Column(Date, nullable=False) # purchase date for lifecycle management
    life_span = Column(Integer, nullable=False, default=0)  # Expected lifespan in months
    desc = Column(String(128), nullable=False) # description for device instance, e.g. installation location or specific notes
    status = Column(SmallInteger, default=1, comment="tiny(1) status")
    device_spec_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to device_specs


class Process(Base):
    """Device combo specification entity model"""

    __tablename__ = "process"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), default=uuid.uuid4, index=False)
    code = Column(String(8), nullable=False, unique=True, index=True)
    name = Column(String(64), nullable=False)
    status = Column(SmallInteger, default=1, comment="tiny(1) status")


class ProcessItem(Base):
    """Device combo detail entity model"""

    __tablename__ = "process_item"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    process_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to processes
    device_spec_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    qty = Column(Integer, nullable=False, default=1)

    
class ProcessDevice(Base):
    """Device combo instance entity model"""

    __tablename__ = "device_combo_inst"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(8), nullable=False, unique=True, index=True)
    device_combo_spec_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to device_combo_specs
    sn = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(SmallInteger, default=1, comment="tiny(1) status")
    
    def __repr__(self):
        return f"<DeviceComboInst {self.id}: {self.code} - {self.sn}>"

class ProcessDeviceItem(Base):
    """Device combo instance detail entity model"""

    __tablename__ = "device_combo_inst_item"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(16), nullable=False, unique=True, index=True)
    desc = Column(String(128), nullable=False)
    device_inst_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to device_insts
    device_combo_inst_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to device_combo_insts

class DeviceInstTag(Base):
    """Device instance tag entity model"""

    __tablename__ = "device_inst_tag"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    device_inst_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to device_insts
    point = Column(String(64), nullable=False, index=True)
    sensor_id = Column(Uuid(as_uuid=True), nullable=True, index=True)  # Optional link to sensors
    status = Column(SmallInteger, default=1, comment="tiny(1) status")
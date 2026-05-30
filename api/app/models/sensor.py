"""
Sensor data models
"""

import uuid
from datetime import datetime
from sqlalchemy import Uuid, Column, SmallInteger, Numeric, Integer, String, Float, DateTime, Boolean, Text, BigInteger
from sqlalchemy.orm import relationship

from sqlalchemy.dialects.mysql import JSON as MySQLJSON

from app.models import Base

class PatrolDiagnosticRecord(Base):
    """Patrol diagnostic result record"""

    __tablename__ = "patrol_diagnostic_record"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    sn = Column(String(255), nullable=False, index=True)
    metric = Column(String(64), nullable=False, default="temperature")
    health_status = Column(SmallInteger, nullable=False, default=0, comment="0=正常, 1=需关注, 2=严重异常")
    conclusion = Column(Text, nullable=True)
    details = Column(MySQLJSON, nullable=True, comment="诊断详情列表: [{window, status, metric, desc}, ...]")
    ts = Column(BigInteger, nullable=False, comment="诊断产生时的时间戳(Unix毫秒)")
    created_at = Column(DateTime, default=datetime.utcnow)

class SensorType(Base):
    """Sensor type entity model"""

    __tablename__ = "sensor_type"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(100), nullable=False, unique=True)
    battery = Column(Integer, nullable=False, default=0)  
    network = Column(Integer, nullable=False, default=1)  # Network range in meters
    bluetooth = Column(Boolean, default=False)  # Bluetooth support
    description = Column(Text)

class Sensor(Base):
    """Sensor entity model"""

    __tablename__ = "sensors"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    sn = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    active = Column(Boolean, default=True)
    active_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sensor_batch_id = Column(Uuid(as_uuid=True), nullable=True, index=True)  # Optional link to sensor_batch for batch tracking

    def __repr__(self):
        return f"<Sensor {self.id}: {self.sn}>"

class SensorBatch(Base):
    """Sensor batch entity model"""

    __tablename__ = "sensor_batch"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(255), nullable=False, unique=True)
    qty = Column(Integer, nullable=False)
    description = Column(Text)
    sn = Column(Integer, nullable=False, index=True)  # Common SN prefix for the batch
    status = Column(SmallInteger, default=1, comment="tiny(1) status")
    sensor_type_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to sensor_types
    tenant_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to tenant for multi-tenant support
    created_at = Column(DateTime, default=datetime.utcnow)
    
    sensor_type = relationship(
        "SensorType",
        primaryjoin="foreign(SensorBatch.sensor_type_id) == SensorType.id",
        lazy="selectin",
        uselist=False
    )

class SensorStatus(Base):
    """Sensor status entity model"""

    __tablename__ = "sensor_status"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    sensor_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to sensors
    timestamp = Column(DateTime, default=datetime.utcnow)
    temperature = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)
    vibration = Column(Float, nullable=True)
    battery = Column(Float, nullable=True)
    active = Column(Boolean, default=True)

class SensorMonitoring(Base):
    """Sensor monitoring entity model"""

    __tablename__ = "sensor_monitoring"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    device_inst_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to device_insts
    location_id = Column(Uuid(as_uuid=True), nullable=True, index=True)  # Optional link to location for asset tracking
    sensor_id = Column(Uuid(as_uuid=True), nullable=True, index=True)  # Optional link to sensors
    direction = Column(String(16), nullable=True)  # e.g. 'horizontal' or 'vertical' for sensor connections
    anomaly = Column(SmallInteger, nullable=False, default=0, comment="异常类型: 0=正常, 1=震动异常, 2=温度异常, 3=震动与温度异常")
    ts = Column(BigInteger, nullable=True, comment="异常发生时间戳(Unix毫秒)")
    status = Column(SmallInteger, default=1, comment="tiny(1) status")

    sensor = relationship(
        "Sensor",
        primaryjoin="foreign(SensorMonitoring.sensor_id) == Sensor.id",
        lazy="selectin",
        uselist=False
    )
    location = relationship(
        "Location",
        primaryjoin="foreign(SensorMonitoring.location_id) == Location.id",
        lazy="selectin",
        uselist=False
    )
    device_inst = relationship(
        "DeviceInst",
        primaryjoin="foreign(SensorMonitoring.device_inst_id) == DeviceInst.id",
        lazy="selectin",
        uselist=False
    )


class SensorThreshold(Base):
    """Sensor threshold entity model"""

    __tablename__ = "sensor_threshold"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(8), nullable=False, index=True)  # Link to sensor_types
    metric = Column(SmallInteger, nullable=False)  # e.g. '1: temperature', '2. vibration'
    rt_max_delta = Column(Numeric(10, 4), nullable=False)  # Real-time max delta threshold
    st_max_slope = Column(Numeric(10, 4), nullable=False)
    st_max_amplitude = Column(Numeric(10, 4), nullable=False)
    mt_max_slope = Column(Numeric(10, 4), nullable=False)
    mt_max_amplitude = Column(Numeric(10, 4), nullable=False)
    baseline = Column(Numeric(10, 4), nullable=False)
    tenant_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to tenant for multi-tenant support
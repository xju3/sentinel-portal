"""
Sensor data models
"""

from datetime import datetime
from sqlalchemy import Uuid, Column, Integer, String, Float, DateTime, Boolean, Text

from app.models import Base

class SensorType(Base):
    """Sensor type entity model"""

    __tablename__ = "sensor_type"

    id = Column(Uuid(as_uuid=True), primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    battery_capacity = Column(Integer, nullable=False, default=0)  
    network = Column(Integer, nullable=False, default=1)  # Network range in meters
    bluetooth = Column(Boolean, default=False)  # Bluetooth support
    description = Column(Text)

class Sensor(Base):
    """Sensor entity model"""

    __tablename__ = "sensors"

    id = Column(Uuid(as_uuid=True), primary_key=True, index=True)
    sn = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    battery = Column(Float, default=100.0)
    active = Column(Boolean, default=True)
    active_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sensor_type_id = Column(Uuid(as_uuid=True), nullable=False, index=True)  # Link to sensor_types

    def __repr__(self):
        return f"<Sensor {self.id}: {self.sn}>"
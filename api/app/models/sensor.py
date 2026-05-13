"""
Sensor data models
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text

from app.models import Base


class Sensor(Base):
    """Sensor entity model"""

    __tablename__ = "sensors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    sensor_type = Column(String(100), nullable=False)
    location = Column(String(255))
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Sensor {self.id}: {self.name}>"


class SensorReading(Base):
    """Sensor reading history (metadata in MySQL, actual data in InfluxDB)"""

    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, index=True)
    sensor_id = Column(Integer, nullable=False, index=True)
    reading_time = Column(DateTime, nullable=False, index=True)
    value = Column(Float, nullable=False)
    unit = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<SensorReading {self.id}: sensor={self.sensor_id}, value={self.value}>"

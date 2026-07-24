"""
Weather data models
"""

import uuid
from sqlalchemy import (
    Column,
    String,
    Uuid,
    Numeric,
    DateTime,
)
from pub.models import Base
from datetime import datetime, timezone, timedelta

def get_shanghai_time():
    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)

class Temperature(Base):
    """Ambient temperature entity model"""

    __tablename__ = "temperature"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    region_id = Column(String(16), nullable=False, index=True)
    dt = Column(DateTime, default=get_shanghai_time, nullable=False)
    temperature = Column(Numeric(5, 2), nullable=False, comment="Celsius")

    def __repr__(self):
        return f"<Temperature {self.id}: {self.region_id} at {self.dt} - {self.temperature}C>"

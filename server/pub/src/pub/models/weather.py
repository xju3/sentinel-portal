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
from datetime import datetime

class Temperature(Base):
    """Ambient temperature entity model"""

    __tablename__ = "temperature"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    region_id = Column(String(16), nullable=False, index=True)
    dt = Column(DateTime, default=datetime.utcnow, nullable=False)
    temperature = Column(Numeric(5, 2), nullable=False, comment="Celsius")

    def __repr__(self):
        return f"<Temperature {self.id}: {self.region_id} at {self.dt} - {self.temperature}C>"

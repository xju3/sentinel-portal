"""
Customer data models
"""

import uuid
from sqlalchemy import Column, String, Uuid, Boolean, Date, Integer, SmallInteger

from app.models import Base


class Tenant(Base):
    """Customer entity model"""

    __tablename__ = "tenant"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(12), nullable=False, unique=True, index=True)
    name = Column(String(64), nullable=False)
    host = Column(String(255), nullable=False)
    active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<Tenant {self.id}: {self.code} - {self.name}>"


class TenantSensor(Base):
    """Tenant entity model"""

    __tablename__ = "tenant_sensor"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(Uuid(as_uuid=True), nullable=False, index=False)
    sensor_id = Column(Uuid(as_uuid=True), nullable=False, index=False)
    qty = Column(Integer, nullable=False, default=1)
    trans_date = Column(Date, nullable=False)  # transaction date for inventory changes
    available = Column(Boolean, nullable=False, default=True)


    def __repr__(self):
        return f"<TenantSensor {self.id}: {self.tenant_id} - {self.sensor_id}>"
    
class Supplier(Base):
    """Supplier entity model"""

    __tablename__ = "supplier"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(64), nullable=False, unique=True)
    brand = Column(String(64), nullable=False)
    contact_info = Column(String(255))
    active = Column(Boolean, default=True)
    tenant_id = Column(Uuid(as_uuid=True), nullable=False, default=uuid.uuid4, index=False) # link to tenant for multi-tenant support   

    def __repr__(self):
        return f"<Supplier {self.id}: {self.name}>"

class Contact(Base):
    """Contact entity model"""

    __tablename__ = "contact"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(64), nullable=False)
    mobile = Column(String(20), nullable=True, unique=True)
    email = Column(String(255), nullable=True, unique=True)
    active = Column(Boolean, default=True)
    tenant_id = Column(
        Uuid(as_uuid=True), nullable=False, default=uuid.uuid4, index=False
    )  # link to tenant for multi-tenant support

    def __repr__(self):
        return f"<Contact {self.id}: {self.name}>"

    
class Account(Base):
    """Account entity model"""

    __tablename__ = "account"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    username = Column(String(64), nullable=False, unique=True)
    email = Column(String(255), nullable=True, unique=True)
    mobile = Column(String(20), nullable=True, unique=True)
    flag = Column(SmallInteger, nullable=False, default=2, comment="tinyint: 1=email, 2=mobile")
    password = Column(String(255), nullable=False)
    active = Column(Boolean, default=True)
    contact_id = Column(Uuid(as_uuid=True), nullable=True, index=True)  # Optional link to contacts
    tenant_id = Column(Uuid(as_uuid=True), nullable=False, default=uuid.uuid4, index=False) # link to tenant for multi-tenant support

    def __repr__(self):
        return f"<Account {self.id}: {self.username}>"

class Area(Base):
    """Area entity model"""

    __tablename__ = "area"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(64), nullable=False)
    description = Column(String(255))
    ssid = Column(String(64), nullable=True)  # Optional Wi-Fi SSID for location-based services
    passwd = Column(String(255), nullable=True)  # Optional Wi-Fi password for location-based services
    parent_id = Column(Uuid(as_uuid=True), nullable=True, index=True)  # For hierarchical area structure
    tenant_id = Column(Uuid(as_uuid=True), nullable=False, default=uuid.uuid4, index=False) # link to tenant for multi-tenant support

    def __repr__(self):
        return f"<Area {self.id}: {self.name}>"

        
class Location(Base):
    """Location entity model"""

    __tablename__ = "location"
    
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)   
    name = Column(String(64), nullable=False)
    description = Column(String(255))
    status  = Column(SmallInteger, nullable=False, default=1)  # tinyint(1) for status
    tenant_id = Column(Uuid(as_uuid=True), nullable=False, default=uuid.uuid4, index=False) # link to tenant for multi-tenant support

    
class HealthCheckFreq(Base):
    """Health check frequency entity model"""

    __tablename__ = "health_check_freq"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    patrol = Column(Integer, nullable=False, default=60) # patrol frequency in minutes (1 hour)
    diagnosis = Column(Integer, nullable=False, default=1440) # diagnosis frequency in minutes (24 hours)
    report = Column(Integer, nullable=False, default=1)  # the mount of accumulated messages to report
    status = Column(Boolean, nullable=False, default=True)
    tenant_id = Column(Uuid(as_uuid=True), nullable=False, index=False)

    def __repr__(self):
        return f"<HealthCheckFreq {self.id}: {self.tenant_id} - {self.device_id}>"

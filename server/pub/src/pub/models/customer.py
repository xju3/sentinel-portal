"""
Customer data models
"""

import uuid
from sqlalchemy import (
    Column,
    String,
    Uuid,
    Boolean,
    Numeric,
    Date,
    Integer,
    SmallInteger,
)
from sqlalchemy.orm import relationship

from pub.models import Base


class Region(Base):
    __tablename__ = "region"
    id = Column(String(16), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(64), nullable=False)
    province = Column(String(16), nullable=False)  # province code
    prefecture = Column(String(16), nullable=False)  # prefectures code
    county = Column(String(16), nullable=False)  # county code
    cnt = Column(Integer, default=0, nullable=False)  # number of sensors.
    abbreviation = Column(String(16), nullable=True)
    parent_id = Column(
        String(16), nullable=True, index=True
    )  # For hierarchical region structure
    level = Column(Integer, nullable=False, default=1)
    available = Column(Boolean, default=True)
    lat = Column(Numeric(10, 6), nullable=True)  # latitude
    lng = Column(Numeric(10, 6), nullable=True)  # longitude

    def __repr__(self):
        return f"<Region {self.id}: {self.name}>"


class Tenant(Base):
    """Customer entity model"""

    __tablename__ = "tenant"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(12), nullable=False, unique=True, index=True)
    name = Column(String(64), nullable=False)
    mqtt_server = Column(String(255), nullable=False, default="mqtt.api-server.icu")
    api_server = Column(String(255), nullable=False, default="api.api-server.icu")
    region_id = Column(String(16), nullable=False, index=True)
    active = Column(Boolean, default=True)
    create_at = Column(Date, nullable=False)
    start_at = Column(
        Date, nullable=False
    )  # The date when the tenant started using the service

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
    tenant_id = Column(
        Uuid(as_uuid=True), nullable=False, default=uuid.uuid4, index=False
    )  # link to tenant for multi-tenant support

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
    username = Column(
        String(255),
        nullable=False,
        unique=True,
        comment="Can be email or mobile phone number",
    )
    flag = Column(
        SmallInteger, nullable=False, default=2, comment="tinyint: 1=email, 2=mobile"
    )
    password = Column(String(255), nullable=False)
    active = Column(Boolean, default=True)
    admin = Column(Boolean, default=False, comment="Whether the account is an admin")
    # wx_access_token = Column(String(255), nullable=True)
    wx_user_id = Column(String(255), nullable=True)
    contact_id = Column(
        Uuid(as_uuid=True), nullable=True, index=True
    )  # Optional link to contacts
    employee_id = Column(
        Uuid(as_uuid=True), nullable=True, index=True
    )  # Optional link to employees
    tenant_id = Column(
        Uuid(as_uuid=True), nullable=False, default=uuid.uuid4, index=False
    )  # link to tenant for multi-tenant support

    def __repr__(self):
        return f"<Account {self.id}: {self.username}>"


class Area(Base):
    """Area entity model"""

    __tablename__ = "area"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(64), nullable=False)
    description = Column(String(255))
    network = Column(
        SmallInteger, nullable=False, default=1
    )  # network type, 1: 4G,  2: Wi-Fi
    ssid = Column(
        String(64), nullable=True
    )  # Optional Wi-Fi SSID for location-based services
    passwd = Column(
        String(255), nullable=True
    )  # Optional Wi-Fi password for location-based services
    parent_id = Column(
        Uuid(as_uuid=True), nullable=True, index=True
    )  # For hierarchical area structure
    tenant_id = Column(
        Uuid(as_uuid=True), nullable=False, default=uuid.uuid4, index=False
    )  # link to tenant for multi-tenant support

    parent = relationship(
        "Area",
        primaryjoin="foreign(Area.parent_id) == remote(Area.id)",
        lazy="selectin",
        uselist=False,
    )

    def __repr__(self):
        return f"<Area {self.id}: {self.name}>"


class Location(Base):
    """Location entity model"""

    __tablename__ = "location"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(64), nullable=False)
    description = Column(String(255))
    status = Column(SmallInteger, nullable=False, default=1)  # tinyint(1) for status
    tenant_id = Column(
        Uuid(as_uuid=True), nullable=False, default=uuid.uuid4, index=False
    )  # link to tenant for multi-tenant support


class HealthCheckFreq(Base):
    """Health check frequency entity model"""

    __tablename__ = "health_check_freq"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    patrol = Column(
        Numeric(10, 2), nullable=False, default=60.0
    )  # patrol frequency in minutes (1 hour)
    diagnosis = Column(
        Numeric(10, 2), nullable=False, default=1440.0
    )  # diagnosis frequency in minutes (24 hours)
    report = Column(
        Integer, nullable=False, default=1
    )  # the mount of accumulated messages to report
    status = Column(Boolean, nullable=False, default=True)
    tenant_id = Column(Uuid(as_uuid=True), nullable=False, index=False)

    def __repr__(self):
        return f"<HealthCheckFreq {self.id}: {self.tenant_id} - {self.device_id}>"


class IsoStandard(Base):
    """ISO standard entity model"""

    __tablename__ = "iso_standard"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(
        String(8), nullable=False, unique=True
    )  # user-defined code, max 8 chars
    version = Column(SmallInteger, nullable=False)  # 1: ISO-10816, 2: ISO-20816
    category = Column(SmallInteger, nullable=False)  # version-dependent category code
    foundation = Column(SmallInteger, nullable=False)  # 1: 刚性基础, 2: 柔性基础
    description = Column(String(255))
    tenant_id = Column(Uuid(as_uuid=True), nullable=False, index=False)

    def __repr__(self):
        return f"<IsoStandard {self.id}: {self.code}>"

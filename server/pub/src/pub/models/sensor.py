"""
Sensor data models
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import relationship, backref

from sqlalchemy.dialects.mysql import JSON as MySQLJSON

from pub.models import Base


class PatrolDiagnosticRecord(Base):
    """Patrol diagnostic result record"""

    __tablename__ = "patrol_diagnostic_record"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    sn = Column(String(255), nullable=False, index=True)
    metric = Column(String(64), nullable=False, default="temperature")
    health_status = Column(
        SmallInteger, nullable=False, default=0, comment="0=正常, 1=需关注, 2=严重异常"
    )
    conclusion = Column(Text, nullable=True)
    details = Column(
        MySQLJSON,
        nullable=True,
        comment="诊断详情列表: [{window, status, metric, desc}, ...]",
    )
    ts = Column(BigInteger, nullable=False, comment="诊断产生时的时间戳(Unix毫秒)")
    created_at = Column(DateTime, default=datetime.utcnow)


class SensorFirmware(Base):
    """Sensor firmware entity model"""

    __tablename__ = "firmware"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    version = Column(String(64), nullable=False, unique=True)
    description = Column(Text)
    release_date = Column(DateTime, nullable=True)
    file_url = Column(String(255), nullable=False)
    sensor_type_id = Column(
        Uuid(as_uuid=True), nullable=False, index=True
    )  # Link to sensor_types
    tenant_id = Column(
        Uuid(as_uuid=True), nullable=True, index=True
    )  # Link to tenant for multi-tenant support
    status = Column(SmallInteger, default=0, comment="状态: 1=active, 0=inactive")


class SensorType(Base):
    """Sensor type entity model"""

    __tablename__ = "sensor_type"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(100), nullable=False, unique=True)
    battery = Column(Integer, nullable=False, default=0)
    network = Column(Integer, nullable=False, default=1)  # Network range in meters
    bluetooth = Column(Boolean, default=False)  # Bluetooth support
    description = Column(Text)


class SimCard(Base):
    """SIM card entity model"""

    __tablename__ = "sim_card"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    iccid = Column(String(64), nullable=False, unique=True)  # SIM card ICCID
    carrier = Column(String(64), nullable=False)  # Mobile carrier
    data_plan = Column(String(64), nullable=False)  # Data plan details
    activated_at = Column(Date, nullable=True)  # SIM card activation date
    expires_at = Column(Date, nullable=False)  # SIM card service expiration date
    # 可用服务时间, 例如 "2024-01-01 to 2024-12-31"
    status = Column(
        SmallInteger, default=1, comment="tiny(1) status"
    )  # SIM card status: 1=active, 0=inactive
    bound = Column(
        SmallInteger, default=0, comment="0=未绑定, 1=已绑定"
    )


class Sensor(Base):
    """Sensor entity model"""

    __tablename__ = "sensors"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    sn = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    active = Column(Boolean, default=True)
    sim_id = Column(
        Uuid(as_uuid=True), nullable=True, index=True
    )  # SIM card number for cellular connectivity
    active_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sensor_batch_id = Column(
        Uuid(as_uuid=True), nullable=True, index=True
    )  # Optional link to sensor_batch for batch tracking

    # Define the relationship to SimCard
    sim_card = relationship(
        "SimCard",
        primaryjoin="foreign(Sensor.sim_id) == SimCard.id",
        backref=backref(
            "sensor", uselist=False
        ),  # 修正: 一张SIM卡同一时间只能绑定一个传感器
        lazy="selectin",  # Eagerly load the related SimCard when querying Sensors
        uselist=False,  # A Sensor has at most one SimCard
    )

    def __repr__(self):
        return f"<Sensor {self.id}: {self.sn}>"


class SensorBatch(Base):
    """Sensor batch entity model"""

    __tablename__ = "sensor_batch"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(255), nullable=False, unique=True)
    qty = Column(Integer, nullable=False)
    description = Column(Text)
    sn = Column(
        String(255), nullable=False, index=True
    )  # Common SN prefix for the batch
    status = Column(SmallInteger, default=1, comment="tiny(1) status")
    sensor_type_id = Column(
        Uuid(as_uuid=True), nullable=False, index=True
    )  # Link to sensor_types
    tenant_id = Column(
        Uuid(as_uuid=True), nullable=False, index=True
    )  # Link to tenant for multi-tenant support
    created_at = Column(DateTime, default=datetime.utcnow)

    sensor_type = relationship(
        "SensorType",
        primaryjoin="foreign(SensorBatch.sensor_type_id) == SensorType.id",
        lazy="selectin",
        uselist=False,
    )


class SensorStatus(Base):
    """Sensor status entity model"""

    """
        sn: 传感器序列号，关联到Sensor表的sn字段
        ts: 传感器状态记录的时间戳，单位为Unix毫秒
        temperature: 当前MCU温度读数，单位为摄氏度
        rssi: 传感器当前的信号强度指示，单位为dBm
        voltage: 传感器当前的电池电压，单位为mV
        active: 传感器当前是否处于活跃状态，true表示活跃
    """

    __tablename__ = "sensor_status"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    sn = Column(String(32), nullable=False, index=True)  # Link to sensors
    ts = Column(DateTime, default=datetime.utcnow)
    temperature = Column(Float, nullable=True)
    rssi = Column(Float, nullable=True)
    voltage = Column(Float, nullable=True)
    active = Column(Boolean, default=True)


class CommunicationState(Base):
    """Latest communication state and sequence counter for one sensor."""

    __tablename__ = "communication_state"

    sn = Column(String(255), primary_key=True)
    last_sequence = Column(BigInteger, nullable=False, default=0)
    last_ts_ms = Column(BigInteger, nullable=True, index=True)
    last_duration_ms = Column(Float, nullable=True)
    last_activity_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class CommunicationRecord(Base):
    """One sensor data collection communication timing event."""

    __tablename__ = "communication_record"
    __table_args__ = (
        UniqueConstraint(
            "sn", "sequence", name="uq_sensor_communication_record_sn_sequence"
        ),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    sn = Column(String(255), nullable=False, index=True)
    ts_ms = Column(BigInteger, nullable=False, index=True)
    duration_ms = Column(Float, nullable=False)
    sequence = Column(BigInteger, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class SensorMonitoring(Base):
    """Sensor monitoring entity model"""

    __tablename__ = "sensor_monitoring"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    device_inst_id = Column(
        Uuid(as_uuid=True), nullable=False, index=True
    )  # Link to device_insts
    location_id = Column(
        Uuid(as_uuid=True), nullable=True, index=True
    )  # Optional link to location for asset tracking
    sensor_id = Column(
        Uuid(as_uuid=True), nullable=True, index=True
    )  # Optional link to sensors
    direction = Column(
        String(16), nullable=True
    )  # e.g. 'horizontal' or 'vertical' for sensor connections
    anomaly = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="异常类型: 0=正常, 1=震动异常, 2=温度异常, 3=震动与温度异常",
    )
    ts = Column(BigInteger, nullable=True, comment="异常发生时间戳(Unix毫秒)")
    status = Column(SmallInteger, default=1, comment="tiny(1) status")

    sensor = relationship(
        "Sensor",
        primaryjoin="foreign(SensorMonitoring.sensor_id) == Sensor.id",
        lazy="selectin",
        uselist=False,
    )
    location = relationship(
        "Location",
        primaryjoin="foreign(SensorMonitoring.location_id) == Location.id",
        lazy="selectin",
        uselist=False,
    )
    device_inst = relationship(
        "DeviceInst",
        primaryjoin="foreign(SensorMonitoring.device_inst_id) == DeviceInst.id",
        lazy="selectin",
        uselist=False,
        overlaps="sensor_monitorings",
    )


class SensorThreshold(Base):
    """Sensor threshold entity model"""

    __tablename__ = "sensor_threshold"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(8), nullable=False, index=True)  # Link to sensor_types
    metric = Column(
        SmallInteger, nullable=False
    )  # e.g. '1: temperature', '2. vibration'
    rt_max_delta = Column(
        Numeric(10, 4), nullable=False
    )  # Real-time max delta threshold
    st_max_slope = Column(Numeric(10, 4), nullable=False)
    st_max_amplitude = Column(Numeric(10, 4), nullable=False)
    mt_max_slope = Column(Numeric(10, 4), nullable=False)
    mt_max_amplitude = Column(Numeric(10, 4), nullable=False)
    baseline = Column(Numeric(10, 4), nullable=False)
    tenant_id = Column(
        Uuid(as_uuid=True), nullable=False, index=True
    )  # Link to tenant for multi-tenant support


class SensorTask(Base):
    """Sensor task entity model.

    action < 10 is reserved for device system tasks:
    0=firmware upgrade, 1=config update, 3=status report.

    status values:
    0=pending delivery, 2=dispatched/running, 1=complete.

    action > 10 is used for temporary collection tasks:
    - 11..99: default-parameter dense collection. The code is T I:
      T = focus type, I = interval minutes. Focus types are 1=general,
      2=temperature, 3=RMS, 4=impact/spectrum.
      Example: action=15, val=3 means collect full data every 5 minutes,
      repeat 3 times.
      Example: action=25, val=3 means collect full data every 5 minutes,
      repeat 3 times with temperature as the server-side review focus.
    - 1000..9999: IIS3DWB parameterized dense collection. The code is M RR I:
      M = FFT points multiplier of 4096, RR = range_g as 02/04/08/16,
      I = interval minutes. val is repeat count.
      Example: action=2086, val=3 means 2*4096 points, 8g, every 6 minutes,
      repeat 3 times.
    """

    __tablename__ = "sensor_task"
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False)  # 任务名称
    sn = Column(String(255), nullable=False, index=True)  # 传感器序列号
    action = Column(SmallInteger, nullable=False)  # 动作类型
    val = Column(SmallInteger, nullable=False, default=0)  # 执行多少次
    remark = Column(Text, nullable=True)  # 任务内容和发起原因说明
    status = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="0=pending, 1=complete, 2=dispatched",
    )  # 任务状态
    create_time = Column(DateTime, default=datetime.utcnow)  # 任务创建时间
    dispatched_at = Column(DateTime, nullable=True)  # 任务下发时间
    complete_time = Column(DateTime, nullable=True)  # 任务完成时间


class SensorTaskReport(Base):
    """Reports produced by one SensorTask execution.

    Each task report records the upload report_id generated for a specific
    task sequence. A task with val=3 is complete only after sequence 1, 2, and
    3 have all been recorded.
    """

    __tablename__ = "sensor_task_report"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "sequence", name="uq_sensor_task_report_task_sequence"
        ),
    )

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    task_id = Column(
        Uuid(as_uuid=True), ForeignKey("sensor_task.id"), nullable=False, index=True
    )
    sn = Column(String(255), nullable=False, index=True)
    sequence = Column(SmallInteger, nullable=False, index=True)
    report_id = Column(String(64), nullable=False, index=True)
    ts_ms = Column(BigInteger, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class DeviceFftRecord(Base):
    """
    Device FFT Record
    Stores metadata for FFT files uploaded to MinIO via SensorTasks.
    """

    __tablename__ = "device_fft_record"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    task_id = Column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
        unique=True,
        comment="Associated SensorTask ID, also the object_name in MinIO fft bucket",
    )

    sn = Column(String(255), nullable=False, index=True, comment="Sensor SN")
    sensor_id = Column(
        Uuid(as_uuid=True), nullable=True, index=True, comment="Sensor database ID"
    )
    device_inst_id = Column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
        comment="Bound monitored device ID (DeviceInst)",
    )
    tenant_id = Column(
        Uuid(as_uuid=True), nullable=True, index=True, comment="Tenant ID"
    )

    ts_ms = Column(
        BigInteger, nullable=False, index=True, comment="Collection timestamp (ms)"
    )
    fs_hz = Column(Integer, nullable=True, comment="Sampling rate (Hz)")
    points = Column(Integer, nullable=True, comment="FFT points")
    range_g = Column(Integer, nullable=True, comment="Range (g)")

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

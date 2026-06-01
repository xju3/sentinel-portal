"""
Config service - 传感器配置变更监控与任务创建
"""

import logging
from typing import Dict, Set, List, Type
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 每个模型类中，值变更会影响 /sensors/config/{sn} 返回值的字段集合
CONFIG_SENSITIVE_FIELDS: Dict[Type, Set[str]] = {}


def init_sensitive_fields():
    """延迟导入模型并填充敏感字段映射，避免循环导入。"""
    if CONFIG_SENSITIVE_FIELDS:
        return

    from app.models.sensor import SensorMonitoring
    from app.models.device import DeviceInst, DeviceSpec, DeviceCategory
    from app.models.customer import HealthCheckFreq, IsoStandard, Area
    from app.models.device import ProcessDevice, ProcessDeviceItem

    from app.models.customer import Tenant

    CONFIG_SENSITIVE_FIELDS.update({
        SensorMonitoring:    {"device_inst_id"},
        DeviceInst:          {"device_spec_id"},
        DeviceSpec:          {"rpm", "device_category_id"},
        DeviceCategory:      {"iso_standard_id", "health_check_freq_id"},
        IsoStandard:         {"version", "category", "foundation"},
        HealthCheckFreq:     {"patrol", "diagnosis", "report"},
        Tenant:              {"host"},
        Area:                {"ssid", "passwd"},
        ProcessDevice:       {"area_id"},
        ProcessDeviceItem:   {"process_device_id"},
    })


async def find_affected_sns(session: AsyncSession, model_class: Type, obj_id: UUID) -> List[str]:
    """根据模型类和记录 ID，反向追溯所有受影响的 sensor.sn。"""
    from app.models.sensor import Sensor, SensorMonitoring
    from app.models.device import DeviceInst, DeviceSpec, DeviceCategory, ProcessDevice, ProcessDeviceItem
    from app.models.customer import IsoStandard, HealthCheckFreq, Area

    sns: List[str] = []

    from app.models.customer import Tenant

    if model_class is Tenant:
        stmt = (
            select(Sensor.sn)
            .select_from(SensorMonitoring)
            .join(Sensor, Sensor.id == SensorMonitoring.sensor_id)
            .join(DeviceInst, DeviceInst.id == SensorMonitoring.device_inst_id)
            .join(DeviceSpec, DeviceSpec.id == DeviceInst.device_spec_id)
            .join(DeviceCategory, DeviceCategory.id == DeviceSpec.device_category_id)
            .where(DeviceCategory.tenant_id == obj_id)
        )

    elif model_class is SensorMonitoring:
        stmt = (
            select(Sensor.sn)
            .where(SensorMonitoring.id == obj_id, Sensor.id == SensorMonitoring.sensor_id)
        )

    elif model_class is DeviceInst:
        stmt = (
            select(Sensor.sn)
            .select_from(SensorMonitoring)
            .join(Sensor, Sensor.id == SensorMonitoring.sensor_id)
            .where(SensorMonitoring.device_inst_id == obj_id)
        )

    elif model_class is DeviceSpec:
        stmt = (
            select(Sensor.sn)
            .select_from(SensorMonitoring)
            .join(Sensor, Sensor.id == SensorMonitoring.sensor_id)
            .join(DeviceInst, DeviceInst.id == SensorMonitoring.device_inst_id)
            .where(DeviceInst.device_spec_id == obj_id)
        )

    elif model_class is DeviceCategory:
        stmt = (
            select(Sensor.sn)
            .select_from(SensorMonitoring)
            .join(Sensor, Sensor.id == SensorMonitoring.sensor_id)
            .join(DeviceInst, DeviceInst.id == SensorMonitoring.device_inst_id)
            .join(DeviceSpec, DeviceSpec.id == DeviceInst.device_spec_id)
            .where(DeviceSpec.device_category_id == obj_id)
        )

    elif model_class in (IsoStandard, HealthCheckFreq):
        fk_col = (
            DeviceCategory.iso_standard_id if model_class is IsoStandard
            else DeviceCategory.health_check_freq_id
        )
        stmt = (
            select(Sensor.sn)
            .select_from(SensorMonitoring)
            .join(Sensor, Sensor.id == SensorMonitoring.sensor_id)
            .join(DeviceInst, DeviceInst.id == SensorMonitoring.device_inst_id)
            .join(DeviceSpec, DeviceSpec.id == DeviceInst.device_spec_id)
            .join(DeviceCategory, DeviceCategory.id == DeviceSpec.device_category_id)
            .where(fk_col == obj_id)
        )

    elif model_class is Area:
        stmt = (
            select(Sensor.sn)
            .select_from(SensorMonitoring)
            .join(Sensor, Sensor.id == SensorMonitoring.sensor_id)
            .join(DeviceInst, DeviceInst.id == SensorMonitoring.device_inst_id)
            .join(ProcessDeviceItem, ProcessDeviceItem.device_inst_id == DeviceInst.id)
            .join(ProcessDevice, ProcessDevice.id == ProcessDeviceItem.process_device_id)
            .where(ProcessDevice.area_id == obj_id)
        )

    elif model_class is ProcessDevice:
        stmt = (
            select(Sensor.sn)
            .select_from(SensorMonitoring)
            .join(Sensor, Sensor.id == SensorMonitoring.sensor_id)
            .join(DeviceInst, DeviceInst.id == SensorMonitoring.device_inst_id)
            .join(ProcessDeviceItem, ProcessDeviceItem.device_inst_id == DeviceInst.id)
            .where(ProcessDeviceItem.process_device_id == obj_id)
        )

    elif model_class is ProcessDeviceItem:
        stmt = (
            select(Sensor.sn)
            .select_from(SensorMonitoring)
            .join(Sensor, Sensor.id == SensorMonitoring.sensor_id)
            .where(SensorMonitoring.device_inst_id == ProcessDeviceItem.device_inst_id)
            .where(ProcessDeviceItem.id == obj_id)
        )

    else:
        return sns

    result = await session.execute(stmt)
    sns = [row[0] for row in result.fetchall()]
    return sns


async def create_config_tasks(session: AsyncSession, sns: List[str]) -> None:
    """为受影响的传感器创建配置更新任务 (SensorTask.action=1, status=0)。
    
    任务写入数据库后，通过 MQTT 向 /sentinel/config/{sn} 下发通知，
    消息体: {"task_id": "<uuid>", "action": 1}
    """
    import json
    from datetime import datetime
    from app.models.sensor import SensorTask
    from app.clients.mqtt import mqtt_manager

    tasks = []
    for sn in sns:
        task = SensorTask(
            name="config_update",
            sn=sn,
            action=1,
            status=0,
            create_time=datetime.utcnow(),
        )
        tasks.append(task)

    session.add_all(tasks)
    await session.commit()
    logger.info(f"[ConfigChange] 已为 {len(sns)} 个传感器创建配置更新任务: {sns}")

    # 为每个任务通过 MQTT 下发通知
    for task in tasks:
        topic = f"/sentinel/config/{task.sn}"
        payload = json.dumps({"task_id": str(task.id), "action": task.action})
        success = mqtt_manager.publish(topic, payload)
        if success:
            logger.info(f"[ConfigChange] MQTT 通知已下发: {topic} -> {payload}")


def core_fields_changed(model_class: Type, old_record, new_data_pydantic) -> bool:
    """检查核心字段是否发生了实际变更（排除 no-op 保存）。"""
    sensitive = CONFIG_SENSITIVE_FIELDS.get(model_class, set())
    if not sensitive:
        return False

    new_values = new_data_pydantic.model_dump(exclude_unset=True)
    logger.debug(f"[ConfigChange] {model_class.__name__} 提交字段: {list(new_values.keys())}")
    if not new_values:
        logger.debug(f"[ConfigChange] {model_class.__name__} 无字段变更（no-op 保存）")
        return False

    for field in sensitive:
        if field in new_values:
            old_val = getattr(old_record, field, None)
            new_val = new_values[field]
            if old_val != new_val:
                logger.info(
                    f"[ConfigChange] {model_class.__name__} 核心字段变更: "
                    f"{field}: {old_val!r} -> {new_val!r}"
                )
                return True
    logger.debug(f"[ConfigChange] {model_class.__name__} 提交字段未涉及核心字段，跳过")
    return False


async def handle_config_change(
    session: AsyncSession,
    model_class: Type,
    obj_id: UUID,
    new_data,
    old_record=None,
) -> None:
    """处理配置变更的完整业务逻辑。

    由 monitor_config_change 装饰器调用。检查核心字段是否变更，
    如果变更则追溯到受影响的传感器列表，记录日志并创建 SensorTask。

    参数:
        session:      数据库会话
        model_class:  SQLAlchemy 模型类
        obj_id:       发生变更的记录 ID
        new_data:     提交的 Pydantic 请求体
        old_record:   CUD 前抓取的旧记录（由装饰器提供）
    """
    init_sensitive_fields()

    logger.info(f"[ConfigChange] 开始检测 {model_class.__name__}(id={obj_id}) 配置变更")

    # 1. 旧记录由装饰器在 CUD 前抓取并传入
    logger.info(f"[ConfigChange] {model_class.__name__}(id={obj_id}) 旧记录: {'存在' if old_record else '不存在'}")

    if old_record is None:
        logger.info(f"[ConfigChange] {model_class.__name__}(id={obj_id}) 旧记录不存在，跳过检测")
        return

    # 2. 检查核心字段是否实际变更
    changed = core_fields_changed(model_class, old_record, new_data)
    logger.info(f"[ConfigChange] {model_class.__name__}(id={obj_id}) 核心字段变更检查: {changed}")
    if not changed:
        logger.info(f"[ConfigChange] {model_class.__name__}(id={obj_id}) 核心字段无变更，跳过")
        return

    # 3. 反向追溯受影响的传感器列表
    logger.info(f"[ConfigChange] {model_class.__name__}(id={obj_id}) 开始反向追溯受影响的传感器...")
    affected_sns = await find_affected_sns(session, model_class, obj_id)
    logger.info(f"[ConfigChange] {model_class.__name__}(id={obj_id}) 追溯完成, 受影响传感器: {affected_sns if affected_sns else '无'}")

    if affected_sns:
        logger.info(
            f"[ConfigChange] {model_class.__name__}(id={obj_id}) 核心字段变更, "
            f"受影响传感器 SN: {affected_sns}"
        )
        # 4. 为每个受影响的传感器创建配置更新任务
        await create_config_tasks(session, affected_sns)
    else:
        logger.info(
            f"[ConfigChange] {model_class.__name__}(id={obj_id}) 核心字段变更, "
            f"无上层传感器关联"
        )

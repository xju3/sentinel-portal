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

    from pub.models.sensor import SensorMonitoring
    from pub.models.device import DeviceInst, DeviceSpec, DeviceCategory
    from pub.models.customer import HealthCheckFreq, IsoStandard, Area
    from pub.models.device import ProcessDevice, ProcessDeviceItem

    from pub.models.customer import Tenant

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
    from pub.models.sensor import Sensor, SensorMonitoring
    from pub.models.device import DeviceInst, DeviceSpec, DeviceCategory, ProcessDevice, ProcessDeviceItem
    from pub.models.customer import IsoStandard, HealthCheckFreq, Area

    sns: List[str] = []

    from pub.models.customer import Tenant

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
    
    对于每个 SN，先检查是否存在 status=0（未完成）的相同任务。
    若存在则跳过创建，避免重复下发；仅当无未完成任务时才新建。

    任务写入数据库后，通过 MQTT 向 /sentinel/task/{sn} 下发通知，
    消息体: {"task_id": "<uuid>", "action": 1, "val": 1}
    """
    import json
    from datetime import datetime
    from pub.models.sensor import SensorTask
    from pub.clients.mqtt import mqtt_manager

    tasks = []
    for sn in sns:
        # 检查是否存在未完成的相同任务 (status=0 表示任务进行中)
        stmt = select(SensorTask).where(
            SensorTask.sn == sn,
            SensorTask.action == 1,
            SensorTask.status == 0,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            logger.info(f"[ConfigChange] SN={sn} 已有未完成的配置更新任务(id={existing.id})，跳过创建")
            continue

        task = SensorTask(
            name="config_update",
            sn=sn,
            action=1,
            val=1,
            status=0,
            create_time=datetime.utcnow(),
        )
        tasks.append(task)

    if not tasks:
        logger.info(f"[ConfigChange] 所有传感器均有未完成任务，无需新建")
        return

    session.add_all(tasks)
    await session.commit()
    logger.info(f"[ConfigChange] 已为 {len(tasks)} 个传感器创建配置更新任务: {[t.sn for t in tasks]}")

    # 为每个任务通过 MQTT 下发通知
    for task in tasks:
        topic = f"/sentinel/task/{task.sn}"
        payload = json.dumps({"task_id": str(task.id), "action": task.action, "val": task.val})
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


async def bg_handle_config_change(
    model_class: Type,
    obj_id: UUID,
    new_data,
    old_values: dict,
) -> None:
    """后台异步任务：对比新旧值，追溯受影响传感器，创建任务，发送 MQTT。

    由 monitor_config_change 装饰器通过 asyncio.create_task 启动，
    不阻塞 HTTP 响应。自行管理数据库 session 生命周期。

    参数:
        model_class: SQLAlchemy 模型类
        obj_id:      记录 ID
        new_data:    提交的 Pydantic 请求体
        old_values:  CUD 前抓取的旧值 dict
    """
    from pub.database import db_manager

    init_sensitive_fields()
    sensitive = CONFIG_SENSITIVE_FIELDS.get(model_class, set())

    logger.info(f"[ConfigChange] 开始检测 {model_class.__name__}(id={obj_id}) 配置变更")

    new_values = new_data.model_dump(exclude_unset=True)
    logger.info(f"[ConfigChange] {model_class.__name__} 提交字段: {list(new_values.keys())}")

    if not new_values:
        logger.info(f"[ConfigChange] {model_class.__name__}(id={obj_id}) 无字段变更（no-op 保存）")
        return

    # Compare old vs new values
    changed = False
    for field in sensitive:
        if field in new_values:
            old_val = old_values.get(field)
            new_val = new_values[field]
            if old_val != new_val:
                logger.info(
                    f"[ConfigChange] {model_class.__name__} 核心字段变更: "
                    f"{field}: {old_val!r} -> {new_val!r}"
                )
                changed = True

    if not changed:
        logger.info(f"[ConfigChange] {model_class.__name__}(id={obj_id}) 核心字段无变更，跳过")
        return

    # Open own DB session for tracing + task creation
    try:
        async for session in db_manager.get_session():
            # 3. Trace affected sensors
            logger.info(f"[ConfigChange] {model_class.__name__}(id={obj_id}) 开始反向追溯受影响的传感器...")
            affected_sns = await find_affected_sns(session, model_class, obj_id)
            logger.info(f"[ConfigChange] {model_class.__name__}(id={obj_id}) 追溯完成, 受影响传感器: {affected_sns if affected_sns else '无'}")

            if affected_sns:
                logger.info(
                    f"[ConfigChange] {model_class.__name__}(id={obj_id}) 核心字段变更, "
                    f"受影响传感器 SN: {affected_sns}"
                )
                # 4. Create tasks + publish MQTT
                await create_config_tasks(session, affected_sns)
            else:
                logger.info(
                    f"[ConfigChange] {model_class.__name__}(id={obj_id}) 核心字段变更, "
                    f"无上层传感器关联"
                )
            break  # Single session iteration
    except Exception as e:
        logger.error(
            f"[ConfigChange] 后台检测 {model_class.__name__}(id={obj_id}) 变更时出错: {e}"
        )

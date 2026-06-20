import logging
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pub.models.sensor import SensorFirmware, SensorBatch, SensorTask
from pub.services.sensor_task_service import (
    SENSOR_TASK_OPEN_STATUSES,
    SENSOR_TASK_STATUS_PENDING,
    SYSTEM_ACTION_FIRMWARE_UPGRADE,
)

logger = logging.getLogger(__name__)

class SensorFirmwareService:
    @staticmethod
    async def get_all(session: AsyncSession, skip: int = 0, limit: int = 100):
        stmt = select(SensorFirmware).order_by(SensorFirmware.version.desc()).offset(skip).limit(limit)
        return (await session.execute(stmt)).scalars().all()

    @staticmethod
    async def get_by_id(session: AsyncSession, obj_id: UUID):
        stmt = select(SensorFirmware).where(SensorFirmware.id == obj_id)
        return (await session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, data: dict):
        obj = SensorFirmware(**data)
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
        return obj

    @staticmethod
    async def update(session: AsyncSession, db_obj: SensorFirmware, data: dict):
        for field, value in data.items():
            setattr(db_obj, field, value)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: SensorFirmware):
        await session.delete(db_obj)
        await session.commit()

    @staticmethod
    async def release_firmware(session: AsyncSession, firmware_id: UUID) -> SensorFirmware:
        stmt = select(SensorFirmware).where(SensorFirmware.id == firmware_id)
        firmware = (await session.execute(stmt)).scalar_one_or_none()
        
        if not firmware:
            raise ValueError("Firmware not found")
        if firmware.status == 1:
            raise ValueError("Firmware has already been released")

        # 1. 查找相关的传感器批次 (定向查找 或 全局查找)
        batch_stmt = select(SensorBatch).where(SensorBatch.sensor_type_id == firmware.sensor_type_id)
        if firmware.tenant_id:
            batch_stmt = batch_stmt.where(SensorBatch.tenant_id == firmware.tenant_id)
        
        batches = (await session.execute(batch_stmt)).scalars().all()

        # 2. 推算出所有目标设备的具体 SN 字符串
        target_sns = {str(batch.sn + i) for batch in batches for i in range(batch.qty)}

        if target_sns:
            # 3. 排除已有未闭环固件升级任务的 SN，防止重复创建任务
            task_stmt = select(SensorTask.sn).where(
                SensorTask.action == SYSTEM_ACTION_FIRMWARE_UPGRADE,
                SensorTask.status.in_(SENSOR_TASK_OPEN_STATUSES),
                SensorTask.sn.in_(target_sns)
            )
            existing_sns = set((await session.execute(task_stmt)).scalars().all())
            
            # 4. 创建新的升级任务
            tasks_to_create = [
                SensorTask(
                    name=f"Firmware Upgrade {firmware.version}",
                    sn=sn,
                    action=SYSTEM_ACTION_FIRMWARE_UPGRADE,
                    val=0,
                    remark=(
                        f"任务内容: 固件升级到 {firmware.version}; "
                        "发起原因: 后台发布新固件; 编码: action=0, val=0"
                    ),
                    status=SENSOR_TASK_STATUS_PENDING,
                    create_time=datetime.utcnow(),
                )
                for sn in target_sns if sn not in existing_sns
            ]
            if tasks_to_create:
                session.add_all(tasks_to_create)

        firmware.status = 1
        firmware.release_date = datetime.utcnow()
        await session.commit()
        await session.refresh(firmware)
        return firmware

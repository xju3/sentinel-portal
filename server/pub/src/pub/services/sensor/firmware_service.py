import json
import logging
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pub.models.sensor import SensorFirmware, SensorBatch, SensorTask, Sensor
from pub.services.sensor.sensor_task_service import (
    SENSOR_TASK_OPEN_STATUSES,
    SENSOR_TASK_STATUS_PENDING,
    SYSTEM_ACTION_FIRMWARE_UPGRADE,
)
from pub.manager.database import db_manager
from pub.services.sensor.firmware_cache_service import SensorOTAContextService

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
        old_status = db_obj.status
        for field, value in data.items():
            setattr(db_obj, field, value)
        await session.commit()
        await session.refresh(db_obj)
        
        # If status changed to inactive, remove cache
        if old_status == 1 and db_obj.status == 0:
            await SensorOTAContextService.remove_active_firmware(
                tenant_id=db_obj.tenant_id,
                sensor_type_id=db_obj.sensor_type_id
            )
        
        return db_obj

    @staticmethod
    async def delete(session: AsyncSession, db_obj: SensorFirmware):
        is_active = db_obj.status == 1
        tenant_id = db_obj.tenant_id
        sensor_type_id = db_obj.sensor_type_id
        
        await session.delete(db_obj)
        await session.commit()
        
        if is_active:
            await SensorOTAContextService.remove_active_firmware(
                tenant_id=tenant_id,
                sensor_type_id=sensor_type_id
            )

    @staticmethod
    async def release_firmware(session: AsyncSession, firmware_id: UUID) -> SensorFirmware:
        stmt = select(SensorFirmware).where(SensorFirmware.id == firmware_id)
        firmware = (await session.execute(stmt)).scalar_one_or_none()
        
        if not firmware:
            raise ValueError("Firmware not found")
        if firmware.status == 1:
            raise ValueError("Firmware has already been released")

        # 仅在当前事务中更新状态为已发布，具体的任务下发交给后台任务进行
        firmware.status = 1
        firmware.release_date = datetime.utcnow()
        await session.commit()
        await session.refresh(firmware)
        
        # 缓存最新固件
        await SensorOTAContextService.cache_active_firmware(
            tenant_id=firmware.tenant_id,
            sensor_type_id=firmware.sensor_type_id,
            firmware_id=firmware.id,
            file_url=firmware.file_url,
            version=firmware.version
        )
        
        return firmware

    @staticmethod
    async def _do_release_firmware_background(firmware_id: UUID):
        try:
            async with db_manager.SessionLocal() as session:
                stmt = select(SensorFirmware).where(SensorFirmware.id == firmware_id)
                firmware = (await session.execute(stmt)).scalar_one_or_none()
                if not firmware:
                    logger.error(f"Background release firmware task failed: Firmware {firmware_id} not found")
                    return
                    
                # 1. 查找符合条件的 Sensor 的 sn。需要是此租户(如果有)以及此传感器类型关联的批次内的实际已注册传感器
                sensor_stmt = select(Sensor.sn).join(
                    SensorBatch, Sensor.sensor_batch_id == SensorBatch.id
                ).where(
                    SensorBatch.sensor_type_id == firmware.sensor_type_id
                )
                if firmware.tenant_id:
                    sensor_stmt = sensor_stmt.where(SensorBatch.tenant_id == firmware.tenant_id)
                
                target_sns = set((await session.execute(sensor_stmt)).scalars().all())

                if target_sns:
                    target_sns_list = list(target_sns)
                    chunk_size = 500
                    
                    for i in range(0, len(target_sns_list), chunk_size):
                        chunk_sns = target_sns_list[i:i+chunk_size]
                        
                        # 排除已有未闭环固件升级任务的 SN，防止重复创建任务
                        task_stmt = select(SensorTask.sn).where(
                            SensorTask.action == SYSTEM_ACTION_FIRMWARE_UPGRADE,
                            SensorTask.status.in_(SENSOR_TASK_OPEN_STATUSES),
                            SensorTask.sn.in_(chunk_sns)
                        )
                        existing_sns = set((await session.execute(task_stmt)).scalars().all())
                        
                        # 创建新的升级任务
                        tasks_to_create = [
                            SensorTask(
                                name=f"Firmware Upgrade {firmware.version}",
                                sn=sn,
                                action=SYSTEM_ACTION_FIRMWARE_UPGRADE,
                                val=0,
                                remark=f"任务内容: 固件升级到 {firmware.version}; 发起原因: 后台发布新固件",
                                status=SENSOR_TASK_STATUS_PENDING,
                                create_time=datetime.utcnow(),
                            )
                            for sn in chunk_sns if sn not in existing_sns
                        ]
                        
                        if tasks_to_create:
                            session.add_all(tasks_to_create)
                            await session.commit()
                            
                logger.info(f"Background release firmware task completed for Firmware {firmware_id}")
        except Exception as e:
            logger.error(f"Error in _do_release_firmware_background: {e}", exc_info=True)

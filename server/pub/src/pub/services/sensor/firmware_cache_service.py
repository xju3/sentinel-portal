import json
import logging
from uuid import UUID
from typing import Optional, List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pub.manager.database import redis_manager
from pub.models.sensor import SensorFirmware, Sensor, SensorBatch

logger = logging.getLogger(__name__)


class SensorOTAContextService:
    SN_CONTEXT_PREFIX = "sensor_context:sn:"
    FIRMWARE_PREFIX = "firmware:active:"
    PRESIGNED_URL_PREFIX = "firmware:url:"

    @staticmethod
    def _get_redis():
        try:
            return redis_manager.get_client()
        except Exception:
            logger.debug("Redis is not initialized; SensorOTAContextService cache unavailable")
            return None

    @classmethod
    async def cache_sensor_context(cls, sns_data: List[Dict[str, Any]]):
        """
        批量缓存 SN -> 基础属性，在交付生成传感器时调用。
        sns_data 格式: [{"sn": "...", "tenant_id": UUID, "sensor_type_id": UUID, "sensor_batch_id": UUID}, ...]
        """
        client = cls._get_redis()
        if not client:
            return

        try:
            pipeline = client.pipeline()
            for item in sns_data:
                key = f"{cls.SN_CONTEXT_PREFIX}{item['sn']}"
                val = json.dumps({
                    "tenant_id": str(item["tenant_id"]) if item.get("tenant_id") else None,
                    "sensor_type_id": str(item["sensor_type_id"]) if item.get("sensor_type_id") else None,
                    "sensor_batch_id": str(item["sensor_batch_id"]) if item.get("sensor_batch_id") else None,
                })
                pipeline.set(key, val)
            pipeline.execute()
        except Exception as e:
            logger.error(f"Failed to cache sensor contexts: {e}", exc_info=True)

    @classmethod
    async def get_sensor_context(cls, session: AsyncSession, sn: str) -> Optional[Dict[str, Any]]:
        """获取 SN 上下文，带缓存丢失时的懒加载回源"""
        client = cls._get_redis()
        
        # 1. Try Redis cache
        if client:
            try:
                val = client.get(f"{cls.SN_CONTEXT_PREFIX}{sn}")
                if val:
                    return json.loads(val)
            except Exception as e:
                logger.error(f"Failed to get sensor context from cache for sn={sn}: {e}", exc_info=True)
                
        # 2. Cache miss, query DB
        try:
            stmt = (
                select(SensorBatch.tenant_id, SensorBatch.sensor_type_id, SensorBatch.id)
                .join(Sensor, Sensor.sensor_batch_id == SensorBatch.id)
                .where(Sensor.sn == sn)
            )
            result = await session.execute(stmt)
            row = result.first()
            if row:
                context_data = {
                    "tenant_id": str(row.tenant_id) if row.tenant_id else None,
                    "sensor_type_id": str(row.sensor_type_id) if row.sensor_type_id else None,
                    "sensor_batch_id": str(row.id) if row.id else None
                }
                # Backfill cache
                if client:
                    try:
                        key = f"{cls.SN_CONTEXT_PREFIX}{sn}"
                        client.set(key, json.dumps(context_data))
                    except Exception as e:
                        logger.error(f"Failed to backfill sensor context cache for sn={sn}: {e}")
                return context_data
        except Exception as e:
            logger.error(f"Failed to query sensor context from DB for sn={sn}: {e}", exc_info=True)
            
        return None

    @classmethod
    async def cache_active_firmware(
        cls, 
        tenant_id: Optional[UUID], 
        sensor_type_id: UUID, 
        firmware_id: UUID, 
        file_url: str, 
        version: str
    ):
        """发布固件 (status=1) 时调用。直接覆盖旧数据。"""
        client = cls._get_redis()
        if not client:
            return
            
        t_id_str = str(tenant_id) if tenant_id else "global"
        key = f"{cls.FIRMWARE_PREFIX}{t_id_str}_{sensor_type_id}"
        
        try:
            val = json.dumps({
                "id": str(firmware_id),
                "file_url": file_url,
                "version": version,
                "status": 1
            })
            client.set(key, val)
        except Exception as e:
            logger.error(f"Failed to cache active firmware {firmware_id}: {e}", exc_info=True)

    @classmethod
    async def remove_active_firmware(cls, tenant_id: Optional[UUID], sensor_type_id: UUID):
        """
        当下线、撤回或删除最新固件 (status=0) 时调用。清除该 key。
        下次请求时会触发回源查询，找出上一版本的活跃固件。
        """
        client = cls._get_redis()
        if not client:
            return
            
        t_id_str = str(tenant_id) if tenant_id else "global"
        key = f"{cls.FIRMWARE_PREFIX}{t_id_str}_{sensor_type_id}"
        
        try:
            client.delete(key)
        except Exception as e:
            logger.error(f"Failed to remove active firmware cache for {t_id_str}_{sensor_type_id}: {e}", exc_info=True)

    @classmethod
    async def cache_empty_firmware_marker(cls, tenant_id: str | None, sensor_type_id: str):
        """缓存空标记，防止缓存穿透，TTL为5分钟"""
        client = cls._get_redis()
        if not client:
            return
            
        t_id_str = tenant_id if tenant_id else "global"
        key = f"{cls.FIRMWARE_PREFIX}{t_id_str}_{sensor_type_id}"
        
        try:
            # {"status": 0} 代表确认无活跃固件
            val = json.dumps({"status": 0})
            client.setex(key, 300, val) # 过期时间 300 秒
        except Exception as e:
            logger.error(f"Failed to cache empty firmware marker for {t_id_str}_{sensor_type_id}: {e}", exc_info=True)

    @classmethod
    async def get_active_firmware(
        cls, 
        session: AsyncSession, 
        tenant_id: str | None, 
        sensor_type_id: str
    ) -> Optional[Dict[str, Any]]:
        """获取活跃固件信息，如果缓存失效则回源查询。"""
        client = cls._get_redis()
        if not client:
            return None
            
        t_id_str = tenant_id if tenant_id else "global"
        key = f"{cls.FIRMWARE_PREFIX}{t_id_str}_{sensor_type_id}"
        
        try:
            # 1. 尝试从 Redis 取
            val = client.get(key)
            if val:
                data = json.loads(val)
                if data.get("status") == 1:
                    return data
                else:
                    # 命中了空标记 {"status": 0}，直接返回 None
                    return None
        except Exception as e:
            logger.error(f"Failed to read active firmware cache: {e}")
            
        # 2. Redis Miss: 触发数据库回源
        try:
            stmt = select(SensorFirmware).where(
                SensorFirmware.sensor_type_id == UUID(sensor_type_id),
                SensorFirmware.status == 1
            )
            if tenant_id and tenant_id != "global":
                stmt = stmt.where(SensorFirmware.tenant_id == UUID(tenant_id))
            else:
                stmt = stmt.where(SensorFirmware.tenant_id.is_(None))
                
            stmt = stmt.order_by(SensorFirmware.release_date.desc()).limit(1)
            latest_fw = (await session.execute(stmt)).scalar_one_or_none()
            
            if latest_fw:
                await cls.cache_active_firmware(
                    tenant_id=latest_fw.tenant_id,
                    sensor_type_id=latest_fw.sensor_type_id,
                    firmware_id=latest_fw.id,
                    file_url=latest_fw.file_url,
                    version=latest_fw.version
                )
                return {
                    "id": str(latest_fw.id),
                    "file_url": latest_fw.file_url,
                    "version": latest_fw.version,
                    "status": 1
                }
            else:
                # 数据库也没有，写入空标记防穿透
                await cls.cache_empty_firmware_marker(tenant_id, sensor_type_id)
                
                # 3. 尝试 Fallback 到 global 固件 (前提是本次查的不是 global)
                if tenant_id and tenant_id != "global":
                    return await cls.get_active_firmware(session, None, sensor_type_id)
                return None
                
        except Exception as e:
            logger.error(f"Failed during database fallback for active firmware: {e}", exc_info=True)
            return None

    @classmethod
    def get_cached_presigned_url(cls, firmware_id: str, file_url: str, version: str) -> str:
        """获取签名URL，使用 Redis 缓存 20 小时以复用"""
        client = cls._get_redis()
        key = f"{cls.PRESIGNED_URL_PREFIX}{firmware_id}"
        
        if client:
            try:
                cached_url = client.get(key)
                if cached_url:
                    return cached_url
            except Exception as e:
                logger.error(f"Failed to read presigned url cache: {e}")

        # 生成新的 URL，有效期 24 小时
        from pub.manager.database import minio_manager
        base_url = minio_manager.get_presigned_url(file_url)
        new_url = f"{base_url}&ver={version}" if "?" in base_url else f"{base_url}?ver={version}"
        
        # 缓存 20 小时，留出 4 小时的冗余给设备下载
        if client:
            try:
                client.setex(key, 20 * 3600, new_url)
            except Exception as e:
                logger.error(f"Failed to cache presigned url: {e}")
                
        return new_url

"""
Database connections and utilities
Handles MySQL, Redis, InfluxDB, and MinIO connections
"""

import logging
from typing import AsyncGenerator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
import redis
from influxdb_client import InfluxDBClient
from minio import Minio
from minio.error import S3Error

from app.config import settings

logger = logging.getLogger(__name__)


# ===== MySQL Database =====
class DatabaseManager:
    """Manager for MySQL database connections"""

    def __init__(self):
        self.engine = None
        self.SessionLocal = None

    async def init(self) -> None:
        """Initialize database engine and session factory"""
        try:
            self.engine = create_async_engine(
                settings.mysql_url,
                echo=settings.debug,
                poolclass=NullPool,  # Disable connection pooling for now
                pool_pre_ping=True,  # Verify connection before use
            )
            self.SessionLocal = async_sessionmaker(
                self.engine, class_=AsyncSession, expire_on_commit=False
            )
            logger.info("MySQL database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MySQL database: {e}")
            raise

    async def close(self) -> None:
        """Close database engine"""
        if self.engine:
            await self.engine.dispose()
            logger.info("MySQL database closed")

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session"""
        if not self.SessionLocal:
            raise RuntimeError("Database not initialized. Call init() first.")
        async with self.SessionLocal() as session:
            try:
                yield session
            except Exception as e:
                await session.rollback()
                logger.error(f"Session error: {e}")
                raise
            finally:
                await session.close()

    async def health_check(self) -> bool:
        """Check MySQL database health"""
        try:
            async with self.SessionLocal() as session:
                await session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"MySQL health check failed: {e}")
            return False


# ===== Redis Connection =====
class RedisManager:
    """Manager for Redis connections"""

    def __init__(self):
        self.client: Optional[redis.Redis] = None

    def init(self) -> None:
        """Initialize Redis connection"""
        try:
            self.client = redis.from_url(settings.redis_url, decode_responses=True)
            self.health_check()
            logger.info("Redis connection initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
            raise

    def close(self) -> None:
        """Close Redis connection"""
        if self.client:
            self.client.close()
            logger.info("Redis connection closed")

    def health_check(self) -> bool:
        """Check Redis connection health"""
        try:
            if self.client:
                self.client.ping()
                return True
            return False
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False

    def get_client(self) -> redis.Redis:
        """Get Redis client"""
        if not self.client:
            raise RuntimeError("Redis not initialized. Call init() first.")
        return self.client


# ===== InfluxDB Connection =====
class InfluxDBManager:
    """Manager for InfluxDB connections"""

    def __init__(self):
        self.client: Optional[InfluxDBClient] = None

    def init(self) -> None:
        """Initialize InfluxDB connection"""
        try:
            self.client = InfluxDBClient(
                url=settings.influx_url,
                token=settings.influx_token,
                org=settings.influx_org,
            )
            self.health_check()
            logger.info("InfluxDB connection initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize InfluxDB: {e}")
            raise

    def close(self) -> None:
        """Close InfluxDB connection"""
        if self.client:
            self.client.close()
            logger.info("InfluxDB connection closed")

    def health_check(self) -> bool:
        """Check InfluxDB connection health"""
        try:
            if self.client:
                self.client.health()
                return True
            return False
        except Exception as e:
            logger.error(f"InfluxDB health check failed: {e}")
            return False

    def get_client(self) -> InfluxDBClient:
        """Get InfluxDB client"""
        if not self.client:
            raise RuntimeError("InfluxDB not initialized. Call init() first.")
        return self.client


# ===== MinIO Connection =====
class MinIOManager:
    """Manager for MinIO connections"""

    def __init__(self):
        self.client: Optional[Minio] = None

    def init(self) -> None:
        """Initialize MinIO connection"""
        try:
            self.client = Minio(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
            self.health_check()
            self._ensure_bucket()
            logger.info("MinIO connection initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MinIO: {e}")
            raise

    def close(self) -> None:
        """Close MinIO connection"""
        # MinIO client doesn't have a close method
        logger.info("MinIO connection closed")

    def health_check(self) -> bool:
        """Check MinIO connection health"""
        try:
            if self.client:
                self.client.bucket_exists(settings.minio_bucket)
                return True
            return False
        except Exception as e:
            logger.error(f"MinIO health check failed: {e}")
            return False

    def _ensure_bucket(self) -> None:
        """Ensure the default bucket exists, create if not"""
        try:
            if self.client:
                if not self.client.bucket_exists(settings.minio_bucket):
                    self.client.make_bucket(settings.minio_bucket)
                    logger.info(f"Created MinIO bucket: {settings.minio_bucket}")
        except S3Error as e:
            logger.error(f"Error managing MinIO bucket: {e}")

    def get_client(self) -> Minio:
        """Get MinIO client"""
        if not self.client:
            raise RuntimeError("MinIO not initialized. Call init() first.")
        return self.client


# Global instances
db_manager = DatabaseManager()
redis_manager = RedisManager()
influxdb_manager = InfluxDBManager()
minio_manager = MinIOManager()

import logging
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from pub.models import Base, import_all_models

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manager for MySQL database connections"""

    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self._mysql_url: str = ""
        self._debug: bool = False
        self._schema_ready: bool = False

    async def init(self, mysql_url: str, debug: bool = False) -> None:
        """Initialize database engine and session factory.

        Args:
            mysql_url:  SQLAlchemy async engine URL (e.g. mysql+aiomysql://user:pass@host:port/db)
            debug:      Enable SQL echoing when True.
        """
        try:
            self._mysql_url = mysql_url
            self._debug = debug
            self.engine = create_async_engine(
                mysql_url,
                # echo=debug,
                echo=False,  # 通过 logging 配置控制日志输出，避免 SQL 语句过多时日志过于冗长
                poolclass=NullPool,
                pool_pre_ping=True,
            )
            self.SessionLocal = async_sessionmaker(
                self.engine, class_=AsyncSession, expire_on_commit=False
            )
            self._schema_ready = False
            await self.ensure_schema()
            # logger.info("MySQL database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MySQL database: {e}")
            raise

    async def ensure_schema(self) -> None:
        """Create missing tables for registered SQLAlchemy models."""
        if self.engine is None:
            raise RuntimeError("Database engine not initialized. Call init() first.")
        if self._schema_ready:
            return
        import_all_models()
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await self._migrate_diagnosis_records(conn)
            await self._ensure_diagnosis_record_columns(conn)
            await self._ensure_sensor_task_columns(conn)
            await self._normalize_legacy_firmware_task_actions(conn)
            await self._ensure_account_wx_user_id(conn)
        self._schema_ready = True

    async def _ensure_account_wx_user_id(self, conn) -> None:
        """Add wx_user_id column to account table if missing."""
        exists = await conn.execute(text("SHOW COLUMNS FROM account LIKE 'wx_user_id'"))
        if exists.first() is None:
            await conn.execute(
                text("ALTER TABLE account ADD COLUMN wx_user_id VARCHAR(255) NULL")
            )

    async def _migrate_diagnosis_records(self, conn) -> None:
        """Migrate existing diagnosis_result records to the new diagnosis_record table."""
        exists = await conn.execute(
            text("SHOW COLUMNS FROM diagnosis_result LIKE 'sensor_id'")
        )
        if exists.first() is not None:
            logger.info("Migrating legacy diagnosis_result data to diagnosis_record...")
            try:
                # 1. Insert distinct report_id records into diagnosis_record
                await conn.execute(text("""
                    INSERT IGNORE INTO diagnosis_record 
                    (id, sn, report_ts, sensor_id, sensor_monitoring_id, 
                     device_inst_id, device_spec_id, device_category_id, status, quality_status, created_at, updated_at)
                    SELECT UUID_TO_BIN(report_id), MAX(sn), MAX(report_ts), MAX(sensor_id), MAX(sensor_monitoring_id),
                           MAX(device_inst_id), MAX(device_spec_id), MAX(device_category_id), 
                           'COMPLETED', 0, MIN(created_at), MAX(updated_at)
                    FROM diagnosis_result
                    GROUP BY report_id
                """))
                
                # 2. Drop columns and indexes from diagnosis_result
                columns = [
                    "sensor_id",
                    "sensor_monitoring_id",
                    "device_inst_id",
                    "device_spec_id",
                    "device_category_id",
                ]
                for column in columns:
                    index_name = f"ix_diagnosis_result_{column}"
                    index_exists = await conn.execute(
                        text("SHOW INDEX FROM diagnosis_result WHERE Key_name = :index_name"),
                        {"index_name": index_name},
                    )
                    if index_exists.first() is not None:
                        await conn.execute(text(f"DROP INDEX {index_name} ON diagnosis_result"))
                    
                    await conn.execute(text(f"ALTER TABLE diagnosis_result DROP COLUMN {column}"))
                logger.info("Migration to diagnosis_record completed.")
            except Exception as e:
                logger.error(f"Migration to diagnosis_record failed: {e}")

    async def _ensure_diagnosis_record_columns(self, conn) -> None:
        """Add missing columns to diagnosis_record if it existed prior."""
        exists = await conn.execute(
            text("SHOW COLUMNS FROM diagnosis_record LIKE 'quality_attempts'")
        )
        if exists.first() is None:
            await conn.execute(
                text("ALTER TABLE diagnosis_record ADD COLUMN quality_attempts JSON NULL COMMENT 'Raw quality.attempts array when clipping occurs'")
            )
            
        exists_qs = await conn.execute(
            text("SHOW COLUMNS FROM diagnosis_record LIKE 'quality_status'")
        )
        if exists_qs.first() is None:
            await conn.execute(
                text("ALTER TABLE diagnosis_record ADD COLUMN quality_status INT NOT NULL DEFAULT 0 COMMENT '0:可用, 1:不可用'")
            )

    async def _ensure_sensor_task_columns(self, conn) -> None:
        """Add task metadata columns introduced after sensor_task existed."""
        columns = {
            "remark": "TEXT NULL",
            "dispatched_at": "DATETIME NULL",
        }
        for column, definition in columns.items():
            exists = await conn.execute(
                text("SHOW COLUMNS FROM sensor_task LIKE :column_name"),
                {"column_name": column},
            )
            if exists.first() is None:
                await conn.execute(
                    text(f"ALTER TABLE sensor_task ADD COLUMN {column} {definition}")
                )

    async def _normalize_legacy_firmware_task_actions(self, conn) -> None:
        """Move tasks generated by the old firmware action=2 code to action=0."""
        await conn.execute(
            text(
                "UPDATE sensor_task SET action = 0 "
                "WHERE action = 2 AND name LIKE 'Firmware Upgrade %'"
            )
        )

    async def close(self) -> None:
        """Close database engine"""
        if self.engine:
            await self.engine.dispose()
            self._schema_ready = False
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

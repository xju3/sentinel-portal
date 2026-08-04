import logging
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from pub.models import Base, import_all_models

logger = logging.getLogger(__name__)


async def ensure_process_code_tenant_unique(conn) -> None:
    """Replace the legacy global dg_template.code index with a tenant-scoped one."""
    if conn.dialect.name != "mysql":
        return

    index_count_sql = """
        SELECT COUNT(*)
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'dg_template'
          AND index_name = :index_name
    """
    legacy_result = await conn.execute(
        text(index_count_sql),
        {"index_name": "ix_process_code"},
    )
    scoped_result = await conn.execute(
        text(index_count_sql),
        {"index_name": "uq_process_tenant_code"},
    )
    has_legacy_index = bool(legacy_result.scalar_one())
    has_scoped_index = bool(scoped_result.scalar_one())

    if has_legacy_index and not has_scoped_index:
        await conn.execute(
            text(
                """
                ALTER TABLE `dg_template`
                    DROP INDEX `ix_process_code`,
                    ADD CONSTRAINT `uq_process_tenant_code`
                        UNIQUE (`tenant_id`, `code`)
                """
            )
        )
    elif has_legacy_index:
        await conn.execute(
            text("ALTER TABLE `dg_template` DROP INDEX `ix_process_code`")
        )
    elif not has_scoped_index:
        await conn.execute(
            text(
                """
                ALTER TABLE `dg_template`
                    ADD CONSTRAINT `uq_process_tenant_code`
                        UNIQUE (`tenant_id`, `code`)
                """
            )
        )


async def ensure_device_inst_optional_fields(conn) -> None:
    """Allow device instances to omit purchase date and notes."""
    if conn.dialect.name != "mysql":
        return

    result = await conn.execute(
        text(
            """
            SELECT column_name, is_nullable
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'device_inst'
              AND column_name IN ('purchase_date', 'desc')
            """
        )
    )
    nullable_by_column = {
        row[0]: str(row[1]).upper() == "YES"
        for row in result.fetchall()
    }
    alterations = []
    if not nullable_by_column.get("purchase_date", False):
        alterations.append("MODIFY COLUMN `purchase_date` DATE NULL")
    if not nullable_by_column.get("desc", False):
        alterations.append("MODIFY COLUMN `desc` VARCHAR(128) NULL")
    if alterations:
        await conn.execute(
            text(f"ALTER TABLE `device_inst` {', '.join(alterations)}")
        )


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
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=10,
                pool_recycle=1800,
            )
            self.SessionLocal = async_sessionmaker(
                self.engine, class_=AsyncSession, expire_on_commit=False
            )
            self._schema_ready = False
            await self.ensure_schema()
            logger.info("MySQL database initialized successfully")
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
        self._schema_ready = True

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

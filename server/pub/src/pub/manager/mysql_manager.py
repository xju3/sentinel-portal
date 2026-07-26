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

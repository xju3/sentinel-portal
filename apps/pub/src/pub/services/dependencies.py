"""
Service-level dependencies for FastAPI dependency injection.
Provides database session dependency without exposing db_manager to routers.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator

from pub.database import db_manager


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency.

    This function wraps db_manager.get_session() so that routers
    do not need to import db_manager directly.
    """
    async for session in db_manager.get_session():
        yield session

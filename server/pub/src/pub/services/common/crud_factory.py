"""
Common factory for CRUD services
"""

from uuid import UUID
from typing import List, Optional, Type, TypeVar
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pub.utils.sorting import apply_sorting

T = TypeVar("T")

def get_crud_service(model_class: Type[T]):
    """Factory function to generate basic CRUD services to avoid excessive boilerplate"""
    class StandardService:
        @staticmethod
        async def get_all(
            session: AsyncSession,
            skip: int,
            limit: int,
            sort_by: str | None = None,
            sort_order: str = "ascend",
        ) -> List[T]:
            stmt = select(model_class)
            stmt = apply_sorting(stmt, model_class, sort_by, sort_order)
            stmt = stmt.offset(skip).limit(limit)
            result = await session.execute(stmt)
            return result.scalars().all()

        @staticmethod
        async def get_by_id(session: AsyncSession, obj_id: UUID) -> Optional[T]:
            stmt = select(model_class).where(model_class.id == obj_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

        @staticmethod
        async def create(session: AsyncSession, data: dict) -> T:
            db_obj = model_class(**data)
            session.add(db_obj)
            await session.commit()
            await session.refresh(db_obj)
            return db_obj

        @staticmethod
        async def update(session: AsyncSession, db_obj: T, data: dict) -> T:
            for key, value in data.items():
                setattr(db_obj, key, value)
            await session.commit()
            await session.refresh(db_obj)
            return db_obj

        @staticmethod
        async def delete(session: AsyncSession, db_obj: T) -> None:
            await session.delete(db_obj)
            await session.commit()

    return StandardService

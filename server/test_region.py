import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select

from pub.models.customer import Region
from app.config import settings

async def main():
    try:
        engine = create_async_engine(settings.mysql_url, echo=True)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            stmt = select(Region).where(Region.level == 1)
            result = await session.execute(stmt)
            print("Success:", result.scalars().all())
    except Exception as e:
        print("Error:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

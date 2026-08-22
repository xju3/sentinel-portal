import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

async def main():
    print("test")

if __name__ == "__main__":
    asyncio.run(main())

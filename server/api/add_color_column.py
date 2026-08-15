import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = "mysql+aiomysql://pl:pl098POI@118.195.147.221:3306/platform"

async def main():
    engine = create_async_engine(DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE device_category ADD COLUMN color VARCHAR(20);"))
            print("Successfully added 'color' column to 'device_category'")
        except Exception as e:
            if "Duplicate column name" in str(e):
                print("Column 'color' already exists.")
            else:
                print(f"Error: {e}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())

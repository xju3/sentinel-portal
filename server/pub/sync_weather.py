import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine
from pub.models import Base
# ensure models are registered
import pub.models.__init__
pub.models.__init__.import_all_models()

from pub.models.weather import Temperature
from pub.services.common.weather_service import WeatherService
from pub.manager.database import db_manager, redis_manager

logging.basicConfig(level=logging.INFO)

async def main():
    MYSQL_URL = "mysql+aiomysql://pl:pl098POI@s1:3306/platform"
    REDIS_URL = "redis://:7fd8cuda8dfd@s1:6379/0"
    
    # Initialize pub db_manager
    await db_manager.init(MYSQL_URL, True)
    redis_manager.init(REDIS_URL)
    
    # 1. Create table if it doesn't exist
    async with db_manager.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("Table 'temperature' created or already exists.")
        
    # 2. Fetch temperatures
    async with db_manager.SessionLocal() as session:
        await WeatherService.fetch_and_store_ambient_temperatures(session)
        print("Weather fetch completed.")
        
    await db_manager.close()
    redis_manager.close()

if __name__ == "__main__":
    asyncio.run(main())

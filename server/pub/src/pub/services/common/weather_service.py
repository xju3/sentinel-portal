import asyncio
import logging
import json
from decimal import Decimal
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pub.models.customer import Tenant, Region
from pub.models.weather import Temperature
from pub.manager.database import redis_manager
from pub.utils.redis_keys import REDIS_KEY_DIA_AMBIENT_TEMP

logger = logging.getLogger(__name__)

class WeatherService:
    @staticmethod
    async def fetch_and_store_ambient_temperatures(session: AsyncSession) -> None:
        """
        Fetch ambient temperatures for all active tenants' regions,
        store them in the database, and cache them in Redis.
        """
        # 1. Get unique region_ids from active tenants
        stmt = select(Tenant.region_id).where(Tenant.active == True).distinct()
        result = await session.execute(stmt)
        region_ids = [row[0] for row in result.all()]

        if not region_ids:
            logger.info("No active tenants with regions found. Skipping weather fetch.")
            return

        # 2. Get region details (lat, lng)
        stmt = select(Region).where(Region.id.in_(region_ids))
        result = await session.execute(stmt)
        regions = result.scalars().all()

        redis_client = redis_manager.client

        async with httpx.AsyncClient(timeout=10.0) as client:
            for region in regions:
                if region.lat is None or region.lng is None:
                    logger.warning("Region %s (%s) has no lat/lng. Skipping.", region.id, region.name)
                    continue

                try:
                    # 3. Call Open-Meteo API
                    # Using the free endpoint for current weather
                    url = f"https://api.open-meteo.com/v1/forecast?latitude={region.lat}&longitude={region.lng}&current_weather=true"
                    response = await client.get(url)
                    response.raise_for_status()
                    data = response.json()
                    
                    if "current_weather" in data and "temperature" in data["current_weather"]:
                        temp_celsius = Decimal(str(data["current_weather"]["temperature"]))
                        
                        # 4. Save to Database
                        new_temp = Temperature(
                            region_id=region.id,
                            temperature=temp_celsius
                        )
                        session.add(new_temp)
                        
                        # 5. Save to Redis for diagnosis context
                        if redis_client:
                            cache_key = REDIS_KEY_DIA_AMBIENT_TEMP.format(region_id=region.id)
                            await asyncio.to_thread(redis_client.set, cache_key, str(temp_celsius), ex=7200)
                            logger.debug("Updated ambient temp for region %s to %sC", region.id, temp_celsius)
                    else:
                        logger.error("Unexpected response from Open-Meteo for region %s: %s", region.id, data)
                        
                except Exception as e:
                    logger.error("Failed to fetch weather for region %s (%s): %s", region.id, region.name, str(e))

        # Commit all new temperature records
        try:
            await session.commit()
            logger.debug("Ambient temperatures successfully fetched and stored.")
        except Exception as e:
            await session.rollback()
            logger.error("Failed to commit ambient temperatures to database: %s", str(e))

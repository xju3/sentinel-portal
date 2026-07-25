import logging

from fastapi import FastAPI
from pydantic import ValidationError

from app.preparation.payload import DeviceDiagnosticReport
from app.preparation.ingestion import process_incoming_report

# Configure basic logging for the new service
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

import asyncio
from contextlib import asynccontextmanager
from pub.manager.database import db_manager, redis_manager, influxdb_manager
from pub.services.common.weather_service import WeatherService
from app.config import settings
from app.clients.mqtt import dia_mqtt_manager, set_main_loop

async def weather_fetch_loop():
    while True:
        try:
            logger.info("Starting scheduled ambient temperature fetch.")
            if db_manager.SessionLocal:
                async with db_manager.SessionLocal() as session:
                    await WeatherService.fetch_and_store_ambient_temperatures(session)
        except Exception as e:
            logger.error("Error in weather fetch loop: %s", str(e))
        
        await asyncio.sleep(3600 * 6)  # 1 hour

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing databases...")
    await db_manager.init(settings.mysql_url, settings.debug)
    redis_manager.init(settings.redis_url)
    influxdb_manager.init(settings.influx_url, settings.influx_token, settings.influx_org, settings.influx_bucket)

    logger.info("Initializing MQTT client...")
    set_main_loop(asyncio.get_running_loop())
    dia_mqtt_manager.init()

    logger.info("Starting background tasks...")
    weather_task = asyncio.create_task(weather_fetch_loop())
    yield
    # Shutdown
    logger.info("Cancelling background tasks...")
    weather_task.cancel()
    try:
        await weather_task
    except asyncio.CancelledError:
        pass
        
    logger.info("Closing databases...")
    await db_manager.close()
    redis_manager.close()
    influxdb_manager.close()

    logger.info("Closing MQTT client...")
    dia_mqtt_manager.close()

app = FastAPI(
    title="Diagnosis API",
    description="New device-centric diagnosis ingestion and execution service.",
    version="1.0.0",
    lifespan=lifespan,
)

@app.post("/api/v1/diagnosis/ingest")
async def ingest_report(report: DeviceDiagnosticReport):
    """
    HTTP endpoint to ingest a diagnostic report payload.
    In a production setup with MQTT, this logic would also be triggered by the MQTT consumer.
    """
    try:
        await process_incoming_report(report)
        return {"status": "success", "message": "Report processed successfully"}
    except Exception as e:
        logger.error("Failed to process report: %s", str(e), exc_info=True)
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)

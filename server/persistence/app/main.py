import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from pub.manager.database import db_manager, minio_manager, redis_manager, influxdb_manager
import logging
from pub.utils.logger import setup_logging
from app.config import settings
from app.clients.stream_worker import start_stream_workers, stop_stream_workers

setup_logging(environment=settings.env, debug=(settings.log_level == "DEBUG"))
logger = logging.getLogger("stl-persistence")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize infrastructure
    logger.info("Initializing MySQL database...")
    await db_manager.init(mysql_url=settings.mysql_url, debug=(settings.log_level == "DEBUG"))

    logger.info("Initializing Redis manager...")
    redis_manager.init(redis_url=settings.redis_url)

    logger.info("Initializing MinIO manager...")
    minio_manager.init(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
        bucket=settings.minio_bucket,
    )
    
    logger.info("Initializing InfluxDB manager...")
    influxdb_manager.init(
        influx_url=settings.influx_url,
        influx_token=settings.influx_token,
        influx_org=settings.influx_org,
        influx_bucket=settings.influx_bucket,
    )

    # Start stream workers
    logger.info("Starting persistence stream workers...")
    await start_stream_workers(settings.stream_worker_count)

    yield

    # Shutdown
    logger.info("Stopping persistence stream workers...")
    await stop_stream_workers()

    minio_manager.close()
    influxdb_manager.close()
    await db_manager.close()
    redis_manager.close()

app = FastAPI(title="STL Persistence API", lifespan=lifespan)

@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}

def start_server():
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=3011, reload=True)

if __name__ == "__main__":
    start_server()

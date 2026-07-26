import logging

from fastapi import FastAPI
from pydantic import ValidationError

from pub.models.report import DeviceDiagnosticReport
from app.preparation.ingestion import process_incoming_report

from pub.utils.logger import setup_logging
from app.config import settings

# Configure logging for the new service using shared pub setup
logger = setup_logging(debug=settings.debug)

import asyncio
from contextlib import asynccontextmanager
from pub.manager.database import db_manager, redis_manager, influxdb_manager, minio_manager
from app.clients.mqtt import dia_mqtt_manager
from app.clients.stream_worker import run_stream_worker, _ensure_consumer_group

# 并发 Worker 数量，控制 MySQL/InfluxDB 并发压力
WORKER_COUNT = 3

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.debug("Initializing databases...")
    await db_manager.init(settings.mysql_url, settings.debug)
    redis_manager.init(settings.redis_url)
    influxdb_manager.init(settings.influx_url, settings.influx_token, settings.influx_org, settings.influx_bucket)
    minio_manager.init(
        settings.minio_endpoint,
        settings.minio_access_key,
        settings.minio_secret_key,
        settings.minio_secure,
        settings.minio_bucket,
    )

    logger.debug("Initializing MQTT client...")
    dia_mqtt_manager.init()

    logger.debug("Initializing Redis Stream consumer group...")
    _ensure_consumer_group()

    logger.debug("Starting background tasks...")
    worker_tasks = [
        asyncio.create_task(run_stream_worker(f"worker-{i}"))
        for i in range(WORKER_COUNT)
    ]
    logger.debug("Started %d stream worker(s).", WORKER_COUNT)
    yield
    # Shutdown
    logger.debug("Cancelling background tasks...")

    logger.debug("Shutting down stream workers...")
    for task in worker_tasks:
        task.cancel()
    await asyncio.gather(*worker_tasks, return_exceptions=True)
        
    logger.debug("Closing databases...")
    await db_manager.close()
    redis_manager.close()
    influxdb_manager.close()
    minio_manager.close()

    logger.debug("Closing MQTT client...")
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

def start_server():
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=3012, reload=True)

if __name__ == "__main__":
    start_server()

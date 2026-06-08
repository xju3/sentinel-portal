"""
Application lifespan management (dia service).

Handles startup (initializing DB, Redis, InfluxDB, MinIO, MQTT client/handler)
and shutdown (gracefully closing all connections) for the FastAPI application.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import db_manager, redis_manager, influxdb_manager, minio_manager
from app.clients.dia_mqtt_client import dia_mqtt_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Startup
    --------
    Initialises all external service connections and starts the MQTT handler.

    Shutdown
    --------
    Gracefully closes each connection in reverse order.
    """
    # ==============================
    # Startup
    # ==============================
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    try:
        await db_manager.init()
        redis_manager.init()
        influxdb_manager.init()
        minio_manager.init()

        # Start MQTT client and register the current module's handler
        dia_mqtt_client.start()

        logger.info("All services initialized successfully")
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

    yield

    # ==============================
    # Shutdown
    # ==============================
    logger.info("Shutting down application")

    # db_manager.close() is async; the rest are sync
    try:
        await db_manager.close()
    except Exception as e:
        logger.error(f"Error shutting down DB: {e}")

    for name, closer in (
        ("Redis", redis_manager.close),
        ("InfluxDB", influxdb_manager.close),
        ("MinIO", minio_manager.close),
    ):
        try:
            closer()
        except Exception as e:
            logger.error(f"Error shutting down {name}: {e}")

    try:
        if dia_mqtt_client.mqtt_manager:
            dia_mqtt_client.mqtt_manager.close()
    except Exception as e:
        logger.error(f"Error shutting down MQTT: {e}")

    logger.info("Shutdown sequence completed")

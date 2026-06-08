"""
Application lifespan management.

Handles startup (initializing DB, Redis, InfluxDB, MinIO, MQTT)
and shutdown (gracefully closing all connections) for the FastAPI application.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from pub.clients.mqtt import mqtt_manager
from app.config import settings
from app.database import db_manager, redis_manager, influxdb_manager, minio_manager
from app.utils import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Startup
    --------
    Initialises all external service connections:
        - MySQL (async via db_manager.init)
        - Redis
        - InfluxDB
        - MinIO
        - MQTT

    Shutdown
    --------
    Gracefully closes each connection in reverse order.
    """
    # ==============================
    # Startup
    # ==============================
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    try:
        await db_manager.init(settings.mysql_url, settings.debug)
        redis_manager.init(settings.redis_url)
        influxdb_manager.init(
            settings.influx_url,
            settings.influx_token,
            settings.influx_org,
            settings.influx_bucket,
        )
        minio_manager.init(
            settings.minio_endpoint,
            settings.minio_access_key,
            settings.minio_secret_key,
            settings.minio_secure,
            settings.minio_bucket,
        )
        mqtt_manager.init()
        logger.info("All services initialized successfully")
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

    yield

    # ==============================
    # Shutdown
    # ==============================
    logger.info("Shutting down application")

    # db_manager.close() is async, the rest are sync
    try:
        await db_manager.close()
    except Exception as e:
        logger.error(f"Error shutting down DB: {e}")

    for name, closer in (
        ("Redis", redis_manager.close),
        ("InfluxDB", influxdb_manager.close),
        ("MinIO", minio_manager.close),
        ("MQTT", mqtt_manager.close),
    ):
        try:
            closer()
        except Exception as e:
            logger.error(f"Error shutting down {name}: {e}")

    logger.info("Shutdown sequence completed")

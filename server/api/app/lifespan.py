"""
Application lifespan management.

Handles startup (initializing DB, Redis, InfluxDB, MinIO, MQTT)
and shutdown (gracefully closing all connections) for the FastAPI application.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from app.clients.mqtt import api_mqtt_manager
from app.config import settings
from app.database import db_manager, redis_manager, influxdb_manager, minio_manager
from pub.models.customer import Tenant
from pub.services import DashboardHealthService
from pub.services.common.weather_service import WeatherService
from app.utils import setup_logging

logger = logging.getLogger(__name__)


async def weather_fetch_loop():
    while True:
        try:
            logger.debug("Starting scheduled ambient temperature fetch.")
            if db_manager.SessionLocal:
                async with db_manager.SessionLocal() as session:
                    await WeatherService.fetch_and_store_ambient_temperatures(session)
        except Exception as e:
            logger.error("Error in weather fetch loop: %s", str(e))
        
        await asyncio.sleep(3600 * 6)  # 6 hours


async def warm_dashboard_snapshots() -> None:
    """Warm missing/stale tenant snapshots after startup without blocking readiness."""
    try:
        if db_manager.SessionLocal is None:
            return
        async with db_manager.SessionLocal() as session:
            tenant_ids = (await session.execute(select(Tenant.id))).scalars().all()
        for tenant_id in tenant_ids:
            await DashboardHealthService.warm_health_dashboard(tenant_id)
    except Exception:
        logger.exception("Dashboard snapshot warmup failed")


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
    logger.debug(f"Starting {settings.app_name} v{settings.app_version}")
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
        api_mqtt_manager.init()
        logger.info("All services initialized successfully")

        logger.debug("Starting background tasks...")
        weather_task = asyncio.create_task(weather_fetch_loop())
        dashboard_warmup_task = asyncio.create_task(warm_dashboard_snapshots())
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

    yield

    # ==============================
    # Shutdown
    # ==============================
    logger.info("Shutting down application")

    logger.debug("Cancelling background tasks...")
    weather_task.cancel()
    dashboard_warmup_task.cancel()
    try:
        await weather_task
    except asyncio.CancelledError:
        pass
    try:
        await dashboard_warmup_task
    except asyncio.CancelledError:
        pass

    # db_manager.close() is async, the rest are sync
    try:
        await db_manager.close()
    except Exception as e:
        logger.error(f"Error shutting down DB: {e}")

    for name, closer in (
        ("Redis", redis_manager.close),
        ("InfluxDB", influxdb_manager.close),
        ("MinIO", minio_manager.close),
        ("MQTT", api_mqtt_manager.close),
    ):
        try:
            closer()
        except Exception as e:
            logger.error(f"Error shutting down {name}: {e}")

    logger.info("Shutdown sequence completed")

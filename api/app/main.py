"""
Main FastAPI application
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import db_manager, redis_manager, influxdb_manager, minio_manager
from app.clients.mqtt import mqtt_manager
from app.clients.handler import patrol_msg_handler
from app.utils.logger import setup_logging
from app.routers import auth, health, sensors, devices, customers, admin, dashboard

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager
    Handles startup and shutdown events
    """
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    try:
        await db_manager.init()
        redis_manager.init()
        influxdb_manager.init()
        minio_manager.init()
        mqtt_manager.init()

        # Inject the running event loop into patrol_msg_handler
        # so it can schedule async DB writes from the sync MQTT callback thread.
        patrol_msg_handler._set_loop(asyncio.get_running_loop())

        logger.info("All services initialized successfully")
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down application")

    try:
        await db_manager.close()
    except Exception as e:
        logger.error(f"Error shutting down DB: {e}")

    try:
        redis_manager.close()
    except Exception as e:
        logger.error(f"Error shutting down Redis: {e}")

    try:
        influxdb_manager.close()
    except Exception as e:
        logger.error(f"Error shutting down InfluxDB: {e}")

    try:
        minio_manager.close()
    except Exception as e:
        logger.error(f"Error shutting down MinIO: {e}")

    try:
        mqtt_manager.close()
    except Exception as e:
        logger.error(f"Error shutting down MQTT: {e}")

    logger.info("Shutdown sequence completed")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="Sensor Portal API for managing sensor data",
    version=settings.app_version,
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(sensors.router, prefix=settings.api_prefix)
app.include_router(customers.router, prefix=settings.api_prefix)
app.include_router(devices.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)
app.include_router(dashboard.router, prefix=settings.api_prefix)

# Root endpoint
@app.get("/")
async def root(request: Request):
    """API root endpoint"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "docs": f"{request.base_url}docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )

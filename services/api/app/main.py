"""
Main FastAPI application
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import json

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Receive, Scope, Send

from pub.clients.mqtt import mqtt_manager
from app.config import settings
from pub.contract.common import ApiResponse
from app.database import db_manager, redis_manager, influxdb_manager, minio_manager
from app.utils import DomainException, setup_logging
from app.routers import auth, health, sensors, devices, customers, admin, dashboard, thresholds, sensor_trends

# Setup logging
setup_logging(settings.environment, settings.debug)
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
        mqtt_manager.init()

        # Inject the running event loop into patrol_msg_handler
        # so it can schedule async DB writes from the sync MQTT callback thread.

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
app.include_router(thresholds.router, prefix=settings.api_prefix)
app.include_router(sensor_trends.router, prefix=settings.api_prefix)



# ==========================================
# Global exception handlers
# ==========================================


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions and return unified ApiResponse format

    All errors are returned with HTTP 200 status code, with the actual error
    code embedded in the response body. This ensures axios treats all responses
    as successful HTTP requests, allowing the frontend interceptor to handle
    business logic errors (code !== 0) uniformly.
    """
    logger.warning(
        "HTTP %d on %s %s: %s",
        exc.status_code,
        request.method,
        request.url.path,
        exc.detail,
    )
    return JSONResponse(
        status_code=200,
        content=jsonable_encoder(
            ApiResponse(code=exc.status_code, message=str(exc.detail), data=None)
        ),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors"""
    errors = exc.errors()
    logger.warning("Validation error on %s %s: %s", request.method, request.url.path, errors)
    return JSONResponse(
        status_code=200,
        content=jsonable_encoder(
            ApiResponse(code=422, message=str(errors), data=None)
        ),
    )


@app.exception_handler(DomainException)
async def domain_exception_handler(request: Request, exc: DomainException):
    """Handle domain/business logic exceptions and return unified ApiResponse format

    DomainException is raised by service layer when business rules are violated
    (e.g. duplicate username, not found, invalid state transition). The handler
    returns HTTP 200 with the business error code embedded in the response body,
    so the frontend interceptor can handle it uniformly.
    """
    logger.warning(
        "Domain error on %s %s: code=%d, message=%s",
        request.method,
        request.url.path,
        exc.code,
        exc.message,
    )
    return JSONResponse(
        status_code=200,
        content=jsonable_encoder(
            ApiResponse(code=exc.code, message=exc.message, data=None)
        ),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=200,
        content=jsonable_encoder(
            ApiResponse(code=500, message="Internal server error", data=None)
        ),
    )


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

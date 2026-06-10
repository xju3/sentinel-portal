"""
Main FastAPI application
"""

import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.lifespan import lifespan
from app.routers import register_routers
from app.utils import setup_logging
from app.utils.exception_handlers import register_exception_handlers

# Setup logging
setup_logging(settings.environment, settings.debug)
logger = logging.getLogger(__name__)

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

# Register routers and exception handlers
register_routers(app)
register_exception_handlers(app)

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

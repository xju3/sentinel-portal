"""
Health check endpoints
"""

from fastapi import APIRouter, Depends, Response

from app.utils.response import success
from app.database import db_manager, redis_manager, influxdb_manager, minio_manager
from pub.contract.health import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check():
    """
    API health check endpoint
    Returns status of all connected services
    """
    services = {
        "mysql": await db_manager.health_check(),
        "redis": redis_manager.health_check(),
        "influxdb": influxdb_manager.health_check(),
        "minio": minio_manager.health_check(),
    }

    all_healthy = all(services.values())
    status = "healthy" if all_healthy else "degraded"

    return success(HealthResponse(
        status=status,
        message="All services operational" if all_healthy else "Some services unavailable",
        services=services,
    ))


@router.get("/live")
async def live_check():
    """Simple liveness probe"""
    return success({"status": "alive"})


@router.get("/ready")
async def ready_check(response: Response):
    """Readiness probe - checks all dependencies"""
    services = {
        "mysql": await db_manager.health_check(),
        "redis": redis_manager.health_check(),
        "influxdb": influxdb_manager.health_check(),
        "minio": minio_manager.health_check(),
    }

    if all(services.values()):
        return success({"status": "ready", "services": services})
    else:
        response.status_code = 503
        return success({"status": "not_ready", "services": services})

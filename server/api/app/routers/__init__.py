"""
API routers

Provides a helper to register all route modules on a FastAPI application.
"""

from fastapi import FastAPI

from app.config import settings
from app.routers import auth, health, sensors, devices, customers, admin, dashboard, dashboard_health, thresholds, sensor_trends, sim_card, wx, org, processes, diagnosis_detail, resend


def register_routers(app: FastAPI) -> None:
    """Register all API routers with the given FastAPI application."""
    app.include_router(sensors.device_router)
    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(sensors.router, prefix=settings.api_prefix)
    app.include_router(customers.router, prefix=settings.api_prefix)
    app.include_router(devices.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(admin.router, prefix=settings.api_prefix)
    app.include_router(dashboard.router, prefix=settings.api_prefix)
    app.include_router(dashboard_health.router, prefix=settings.api_prefix)
    app.include_router(thresholds.router, prefix=settings.api_prefix)
    app.include_router(sensor_trends.router, prefix=settings.api_prefix)
    app.include_router(sim_card.router, prefix=settings.api_prefix)
    app.include_router(wx.router, prefix=settings.api_prefix)
    app.include_router(diagnosis_detail.router, prefix=settings.api_prefix)
    app.include_router(org.router, prefix=settings.api_prefix)
    app.include_router(processes.router, prefix=settings.api_prefix)
    app.include_router(resend.router, prefix=settings.api_prefix)

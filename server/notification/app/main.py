import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from pub.manager.database import db_manager, redis_manager
from pub.models import Base, import_all_models
from pub.models.diagnosis import DiagnosisNotificationDelivery
from pub.services.wx.wx_service import WxService
from pub.utils.logger import setup_logging

from app.clients.mqtt import NotificationMQTTClient
from app.config import settings
from app.services.notification_service import LocalNotificationService
from app.services.worker import NotificationWorker

setup_logging(debug=settings.debug)
logger = logging.getLogger(__name__)


async def ensure_notification_schema() -> None:
    if db_manager.engine is None:
        raise RuntimeError("Database engine not initialized")

    import_all_models()
    _ = DiagnosisNotificationDelivery
    async with db_manager.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db_manager.init(settings.mysql_url, settings.debug)
    redis_manager.init(settings.redis_url)
    await ensure_notification_schema()

    wx_service = WxService(
        app_id=settings.wx_app_id,
        app_secret=settings.wx_app_secret,
        redis_client=redis_manager.get_client(),
    )
    notification_service = LocalNotificationService(
        session_factory=db_manager.SessionLocal,
        wx_service=wx_service,
        settings=settings,
    )
    worker = NotificationWorker(notification_service)
    mqtt_client = NotificationMQTTClient(settings, worker)
    await mqtt_client.start(asyncio.get_running_loop())

    app.state.notification_service = notification_service
    app.state.notification_worker = worker
    app.state.mqtt_client = mqtt_client

    try:
        yield
    finally:
        await mqtt_client.stop()
        redis_manager.close()
        await db_manager.close()


app = FastAPI(
    title="Sentinel Notification Service",
    version=settings.app_version,
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "app": settings.app_name,
        "mqtt_topic": settings.mqtt_notification_topic,
        "wx_template_id": settings.wx_template_id,
    }


def start_server():
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)


if __name__ == "__main__":
    start_server()

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.config import Settings
from app.routers import sensors
from pub.utils.redis_keys import (
    REDIS_KEY_DASHBOARD_HEALTH_DIRTY,
    REDIS_STREAM_PERSISTENCE_INGEST,
)
from pub.utils.redis_url import redis_url_with_db


def test_redis_url_with_db_preserves_credentials_and_options():
    url = "rediss://:secret@redis.internal:6380/0?ssl_cert_reqs=none&db=0"

    assert redis_url_with_db(url, 11) == (
        "rediss://:secret@redis.internal:6380/11?ssl_cert_reqs=none"
    )


def test_api_stream_redis_defaults_to_db_11():
    settings = Settings(redis_url="redis://redis.internal:6379/0", _env_file=None)

    assert settings.stream_redis_url == "redis://redis.internal:6379/11"


@pytest.mark.asyncio
async def test_sensor_upload_publishes_persistence_stream_to_isolated_redis(monkeypatch):
    stream_client = Mock()
    monkeypatch.setattr(
        sensors.stream_redis_manager,
        "get_client",
        Mock(return_value=stream_client),
    )
    monkeypatch.setattr(sensors, "upload_json_to_minio_sync", Mock(return_value=True))
    monkeypatch.setattr(sensors.api_mqtt_manager, "publish", Mock())
    monkeypatch.setattr(
        sensors.SensorCommunicationService,
        "record_from_payload_managed",
        AsyncMock(return_value=None),
    )

    await sensors._process_sensor_data_background_async(
        "STL26SH0001/2026/07/29/16-07-03.json",
        {"sn": "STL26SH0001"},
        "report-id",
    )

    stream_client.xadd.assert_called_once_with(
        REDIS_STREAM_PERSISTENCE_INGEST,
        {
            "bucket": "json",
            "path": "STL26SH0001/2026/07/29/16-07-03.json",
        },
        maxlen=5000,
        approximate=True,
    )


@pytest.mark.asyncio
async def test_sensor_upload_updates_activity_and_invalidates_health_snapshot(monkeypatch):
    tenant_id = uuid4()
    activity = AsyncMock(return_value=object())
    cache_client = Mock()
    monkeypatch.setattr(
        sensors.SensorCommunicationService,
        "record_from_payload_managed",
        activity,
    )
    monkeypatch.setattr(
        sensors.redis_manager,
        "get_client",
        Mock(return_value=cache_client),
    )
    monkeypatch.setattr(sensors, "upload_json_to_minio_sync", Mock(return_value=False))

    payload = {
        "sensor_sn": "STL26SH0001",
        "ts_ms": 1_785_400_000_000,
        "duration_ms": 1_234,
        "tenant_id": str(tenant_id),
    }
    await sensors._process_sensor_data_background_async(
        "STL26SH0001/2026/07/30/17-00-00.json",
        payload,
        "report-id",
    )

    activity.assert_awaited_once_with(payload)
    cache_client.hset.assert_called_once()
    assert cache_client.hset.call_args.args[:2] == (
        REDIS_KEY_DASHBOARD_HEALTH_DIRTY,
        str(tenant_id),
    )

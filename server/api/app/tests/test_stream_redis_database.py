from unittest.mock import Mock

import pytest

from app.config import Settings
from app.routers import sensors
from pub.utils.redis_keys import REDIS_STREAM_PERSISTENCE_INGEST
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

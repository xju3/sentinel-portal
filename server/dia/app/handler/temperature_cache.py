"""
Redis cache for recent temperature points.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional, cast

from app.database import redis_manager

logger = logging.getLogger(__name__)

TEMPERATURE_CACHE_KEY_PREFIX = "dia:temperature:"
TEMPERATURE_CACHE_LIMIT = 72


@dataclass(frozen=True)
class TemperatureCachePoint:
    temp_c: float
    ts_ms: int


def get_recent_temperature_points(sn: str, limit: int = TEMPERATURE_CACHE_LIMIT) -> list[TemperatureCachePoint]:
    """Read recent temperature points from Redis, oldest first."""
    client = _get_redis_client()
    if client is None:
        return []

    try:
        raw_items = cast(list, client.lrange(_cache_key(sn), 0, limit - 1))
    except Exception as e:
        logger.warning("Failed to read temperature cache for sn=%s: %s", sn, e)
        return []

    points = [_parse_cache_point(item) for item in raw_items]
    return [point for point in reversed(points) if point is not None]


def replace_recent_temperature_points(
    sn: str,
    points: list[TemperatureCachePoint],
    limit: int = TEMPERATURE_CACHE_LIMIT,
) -> None:
    """Replace Redis recent temperature cache with points ordered oldest first."""
    client = _get_redis_client()
    if client is None:
        return

    recent_points = points[-limit:]
    key = _cache_key(sn)
    try:
        pipeline = client.pipeline()
        pipeline.delete(key)
        for point in reversed(recent_points):
            pipeline.rpush(key, _serialize_cache_point(point))
        pipeline.ltrim(key, 0, limit - 1)
        pipeline.execute()
    except Exception as e:
        logger.warning("Failed to replace temperature cache for sn=%s: %s", sn, e)


def push_recent_temperature_point(
    sn: str,
    point: TemperatureCachePoint,
    limit: int = TEMPERATURE_CACHE_LIMIT,
) -> None:
    """Push newest temperature point to Redis and keep only the recent window."""
    client = _get_redis_client()
    if client is None:
        return

    try:
        pipeline = client.pipeline()
        pipeline.lpush(_cache_key(sn), _serialize_cache_point(point))
        pipeline.ltrim(_cache_key(sn), 0, limit - 1)
        pipeline.execute()
    except Exception as e:
        logger.warning("Failed to push temperature cache for sn=%s: %s", sn, e)


def _cache_key(sn: str) -> str:
    return f"{TEMPERATURE_CACHE_KEY_PREFIX}{sn}:recent"


def _get_redis_client() -> Any | None:
    try:
        return redis_manager.get_client()
    except RuntimeError:
        logger.warning("Redis is not initialized; temperature cache unavailable")
        return None


def _serialize_cache_point(point: TemperatureCachePoint) -> str:
    return json.dumps(
        {
            "temp_c": point.temp_c,
            "ts_ms": point.ts_ms,
        },
        separators=(",", ":"),
    )


def _parse_cache_point(raw_item: Any) -> Optional[TemperatureCachePoint]:
    try:
        data = json.loads(raw_item)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    temp_c = data.get("temp_c")
    ts_ms = data.get("ts_ms")
    if isinstance(temp_c, bool) or not isinstance(temp_c, (int, float)):
        return None
    if isinstance(ts_ms, bool) or not isinstance(ts_ms, int):
        return None
    return TemperatureCachePoint(temp_c=float(temp_c), ts_ms=ts_ms)

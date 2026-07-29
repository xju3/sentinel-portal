"""
Thin wrapper that re-exports from pub.database and handles config injection.
All imports from app.database will continue to work transparently.
"""

from pub.manager.database import (
    DatabaseManager,
    RedisManager,
    InfluxDBManager,
    MinIOManager,
    db_manager,
    redis_manager,
    influxdb_manager,
    minio_manager,
)

stream_redis_manager = RedisManager()

__all__ = [
    "DatabaseManager",
    "RedisManager",
    "InfluxDBManager",
    "MinIOManager",
    "db_manager",
    "redis_manager",
    "stream_redis_manager",
    "influxdb_manager",
    "minio_manager",
]

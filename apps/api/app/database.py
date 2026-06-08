"""
Thin wrapper that re-exports from pub.database and handles config injection.
All imports from app.database will continue to work transparently.
"""

from pub.database import (
    DatabaseManager,
    RedisManager,
    InfluxDBManager,
    MinIOManager,
    db_manager,
    redis_manager,
    influxdb_manager,
    minio_manager,
)

__all__ = [
    "DatabaseManager",
    "RedisManager",
    "InfluxDBManager",
    "MinIOManager",
    "db_manager",
    "redis_manager",
    "influxdb_manager",
    "minio_manager",
]
"""
Database connections and utilities
Handles MySQL, Redis, InfluxDB, and MinIO connections

Uses config injection: call init() with URL/credentials instead of
reading from a hard-coded app.config module. This makes the module
reusable across api and dia services.
"""

from pub.manager.mysql_manager import DatabaseManager
from pub.manager.redis_manager import RedisManager
from pub.manager.influxdb_manager import InfluxDBManager
from pub.manager.minio_manager import MinIOManager

# Global instances — created once, initialized by each service's startup
db_manager = DatabaseManager()
redis_manager = RedisManager()
influxdb_manager = InfluxDBManager()
minio_manager = MinIOManager()

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

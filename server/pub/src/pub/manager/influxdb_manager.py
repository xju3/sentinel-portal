import logging
from typing import Optional
from influxdb_client import InfluxDBClient

logger = logging.getLogger(__name__)

class InfluxDBManager:
    """Manager for InfluxDB connections"""

    def __init__(self):
        self.client: Optional[InfluxDBClient] = None
        self.org: str = ""
        self.bucket: str = ""

    def init(self, influx_url: str, influx_token: str, influx_org: str, influx_bucket: str = "sentinel-accel-raw-data") -> None:
        """Initialize InfluxDB connection"""
        try:
            self.org = influx_org
            self.bucket = influx_bucket
            self.client = InfluxDBClient(
                url=influx_url,
                token=influx_token,
                org=influx_org,
            )
            self.health_check()
            # logger.info("InfluxDB connection initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize InfluxDB: {e}")
            raise

    def close(self) -> None:
        """Close InfluxDB connection"""
        if self.client:
            self.client.close()
            logger.info("InfluxDB connection closed")

    def health_check(self) -> bool:
        """Check InfluxDB connection health"""
        try:
            if self.client:
                self.client.health()
                return True
            return False
        except Exception as e:
            logger.error(f"InfluxDB health check failed: {e}")
            return False

    def get_client(self) -> InfluxDBClient:
        """Get InfluxDB client"""
        if not self.client:
            raise RuntimeError("InfluxDB not initialized. Call init() first.")
        return self.client

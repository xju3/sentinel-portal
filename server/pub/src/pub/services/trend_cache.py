import asyncio
import logging
from typing import Any
from pub.manager.database import redis_manager

logger = logging.getLogger(__name__)

class TrendCacheService:
    """
    Maintains a highly efficient, sorted in-memory cache (Redis ZSET) of recent metric points 
    specifically optimized for the diagnostic algorithms (e.g., slope calculations).
    This avoids heavy reads on InfluxDB during real-time diagnosis.
    """
    
    # Keep data for the last 72 hours (3 days) by default
    # 72 hours * 60 mins * 60 secs * 1000 ms
    RETENTION_MS = 72 * 60 * 60 * 1000

    @staticmethod
    async def push_metrics(location_id: str, ts_ms: int, metrics: dict[str, float]) -> None:
        """
        Pushes MULTIPLE metrics (e.g., Temp, RMS X/Y/Z) into their respective ZSETs 
        simultaneously using a single Redis Pipeline. 
        """
        client = redis_manager.get_client()
        if client is None or not metrics:
            return

        try:
            pipeline = client.pipeline()
            
            # The cutoff time: anything older than this is evicted
            cutoff_ts_ms = ts_ms - TrendCacheService.RETENTION_MS

            for metric_name, value in metrics.items():
                key = f"dia:trend:{metric_name}:{location_id}"
                member = f"{ts_ms}:{value}"
                
                # 1. Add the new point
                pipeline.zadd(key, {member: ts_ms})
                # 2. Trim the set purely by TIME (Score), not by count!
                # Removes all members with a score between 0 and cutoff_ts_ms
                pipeline.zremrangebyscore(key, 0, cutoff_ts_ms)
            
            # Execute all commands across all ZSETs in exactly 1 network request!
            await asyncio.to_thread(pipeline.execute)
            logger.debug("Pushed %d metrics to trend cache for location_id=%s, cutoff=%s", 
                         len(metrics), location_id, cutoff_ts_ms)
        except Exception as e:
            logger.warning("Failed to push metrics to trend cache for location_id=%s: %s", location_id, e)

    @staticmethod
    async def get_recent_trend(location_id: str, metric_name: str) -> list[dict[str, Any]]:
        """
        Retrieves the perfectly sorted recent trend for the diagnostic algorithms in O(1) time.
        Returns a list of dicts: [{"ts_ms": 123, "value": 31.5}, ...]
        """
        client = redis_manager.get_client()
        if client is None:
            return []

        key = f"dia:trend:{metric_name}:{location_id}"
        try:
            # ZRANGE returns members sorted by score (ts_ms) ascending
            raw_members = await asyncio.to_thread(client.zrange, key, 0, -1)
            
            trend_data = []
            for member in raw_members:
                # member is in format "ts_ms:value"
                if isinstance(member, bytes):
                    member = member.decode("utf-8")
                parts = member.split(":")
                if len(parts) == 2:
                    trend_data.append({
                        "ts_ms": int(parts[0]),
                        "value": float(parts[1])
                    })
            return trend_data
        except Exception as e:
            logger.warning("Failed to fetch trend cache for location_id=%s: %s", location_id, e)
            return []

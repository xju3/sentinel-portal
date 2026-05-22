"""
Redis queue client
Provides Redis-based fixed-length queue operations for MQTT data.
Each device (keyed by SN) maintains a queue with a configurable maximum length.
Queue element structure: {sn, sequence, ts, rms_m, temperature}
"""

import json
import logging
import time
from typing import Any, Optional, cast

import redis

from app.config import settings
from app.database import redis_manager, db_manager
from app.services.customer_service import HealthCheckFreqService

logger = logging.getLogger(__name__)

# Redis key prefix for the data queue
QUEUE_KEY_PREFIX = "mqtt:queue:"
# Redis key prefix for the sequence counter
SEQ_KEY_PREFIX = "mqtt:seq:"
# Redis key prefix for the queue max length cache
QUEUE_MAX_LEN_KEY_PREFIX = "mqtt:maxlen:"


class RedisClient:
    """Client for managing fixed-length Redis queues for device data.

    Each device (identified by SN) has its own queue that maintains
    a configurable maximum number of data points.
    """

    def __init__(self) -> None:
        self._client: Optional[redis.Redis] = None

    def _ensure_redis(self) -> bool:
        """Ensure the Redis client is initialized.

        Returns:
            True if Redis is available, False otherwise.
        """
        if self._client is None:
            try:
                self._client = redis_manager.get_client()
            except RuntimeError:
                logger.error("Redis is not initialized")
                return False
        return True

    async def get_queue_max_len(self, sn: str) -> int:
        """Get the maximum queue length for the given sensor SN.

        First tries to read from Redis cache. If not found, looks up the
        HealthCheckFreq configured for the sensor's device category and
        caches the result in Redis. Falls back to the global default.

        Args:
            sn: The device serial number.

        Returns:
            The queue max length (patrol frequency in data points).
        """
        cache_key = f"{QUEUE_MAX_LEN_KEY_PREFIX}{sn}"

        # 1. Try to get from Redis cache first
        if self._ensure_redis():
            try:
                cached = cast(Optional[str], self._client.get(cache_key))  # type: ignore[union-attr]
                if cached is not None:
                    return int(cached)
            except Exception as e:
                logger.debug(f"Failed to get cached max_len for SN={sn}: {e}")

        # 2. Cache miss — query the database
        try:
            async for session in db_manager.get_session():
                health_check = await HealthCheckFreqService.get_health_check_by_sensor_sn(
                    session, sn
                )
                if health_check is not None and health_check.patrol is not None:
                    patrol_value = cast(int, health_check.patrol)
                    result = int(patrol_value * settings.patrol_queue_length / 60)
                    # Cache the result in Redis with 1-hour TTL
                    if self._ensure_redis():
                        try:
                            self._client.set(cache_key, result)  # type: ignore[union-attr]
                        except Exception as e:
                            logger.debug(f"Failed to cache max_len for SN={sn}: {e}")
                    return result
        except Exception as e:
            logger.warning(
                f"Failed to fetch HealthCheckFreq for SN={sn}, "
                f"falling back to default: {e}"
            )

        # 3. Fall back to the global default
        return settings.patrol_queue_length

    def _get_next_sequence(self, sn: str) -> int:
        """Atomically increment and return the sequence number for the given SN."""
        seq_key = f"{SEQ_KEY_PREFIX}{sn}"
        # INCR returns the new value after increment; starts at 1 on first call
        return self._client.incr(seq_key)  # type: ignore[union-attr]

    async def push_rms_data(self, sn: str, rms_m: float, temperature: float) -> bool:
        """Push rms_m and temperature data into the fixed-length Redis queue for the given SN.

        Constructs a queue element with an auto-incrementing sequence number,
        current timestamp, and the given sensor values, then pushes it into
        the Redis list while maintaining the maximum queue length.

        Args:
            sn: The device serial number.
            rms_m: The RMS composite value.
            temperature: The temperature value.

        Returns:
            True if the data was successfully queued, False otherwise.
        """
        if not self._ensure_redis():
            logger.error(f"Cannot push data for SN={sn}: Redis unavailable")
            return False

        try:
            sequence = self._get_next_sequence(sn)
            ts = time.time()
            queue_max_len = await self.get_queue_max_len(sn)

            queue_key = f"{QUEUE_KEY_PREFIX}{sn}"

            element = json.dumps(
                {
                    "sn": sn,
                    "sequence": sequence,
                    "ts": ts,
                    "rms_m": rms_m,
                    "temperature": temperature,
                }
            )

            # Pipeline the LPUSH and LTRIM for atomicity
            pipeline = self._client.pipeline()  # type: ignore[union-attr]
            pipeline.lpush(queue_key, element)
            pipeline.ltrim(queue_key, 0, queue_max_len - 1)
            pipeline.execute()

            logger.debug(
                f"Queued data for SN={sn}, sequence={sequence}, queue_size={queue_max_len}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to queue message for SN={sn}: {e}")
            return False

    async def get_queue(self, sn: str, start: int = 0, end: Optional[int] = None) -> list:
        """Retrieve elements from the Redis queue for the given SN.

        Args:
            sn: The device serial number.
            start: The starting index (0-based, 0 is the newest).
            end: The ending index (inclusive). Defaults to queue_max_len - 1.

        Returns:
            A list of queue element dicts, or an empty list on failure.
        """
        if not self._ensure_redis():
            logger.error(f"Cannot get queue for SN={sn}: Redis unavailable")
            return []

        if end is None:
            queue_max_len = await self.get_queue_max_len(sn)
            end = queue_max_len - 1

        try:
            queue_key = f"{QUEUE_KEY_PREFIX}{sn}"
            elements = cast(list, self._client.lrange(queue_key, start, end))  # type: ignore[union-attr]
            return [json.loads(elem) for elem in elements]
        except Exception as e:
            logger.error(f"Failed to get queue for SN={sn}: {e}")
            return []

    def get_queue_length(self, sn: str) -> int:
        """Get the current length of the Redis queue for the given SN.

        Args:
            sn: The device serial number.

        Returns:
            The queue length, or 0 on failure.
        """
        if not self._ensure_redis():
            logger.error(f"Cannot get queue length for SN={sn}: Redis unavailable")
            return 0

        try:
            queue_key = f"{QUEUE_KEY_PREFIX}{sn}"
            return self._client.llen(queue_key)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Failed to get queue length for SN={sn}: {e}")
            return 0

    def clear_queue(self, sn: str) -> bool:
        """Clear the Redis queue and sequence counter for the given SN.

        Args:
            sn: The device serial number.

        Returns:
            True if cleared successfully, False otherwise.
        """
        if not self._ensure_redis():
            logger.error(f"Cannot clear queue for SN={sn}: Redis unavailable")
            return False

        try:
            queue_key = f"{QUEUE_KEY_PREFIX}{sn}"
            seq_key = f"{SEQ_KEY_PREFIX}{sn}"
            pipeline = self._client.pipeline()  # type: ignore[union-attr]
            pipeline.delete(queue_key)
            pipeline.delete(seq_key)
            pipeline.execute()
            logger.debug(f"Cleared queue and sequence for SN={sn}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear queue for SN={sn}: {e}")
            return False


# Global instance
redis_client = RedisClient()

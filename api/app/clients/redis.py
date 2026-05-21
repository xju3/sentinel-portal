"""
Redis queue client
Provides Redis-based fixed-length queue operations for MQTT data.
Each device (keyed by SN) maintains a queue with a configurable maximum length.
Queue element structure: {sn, sequence, ts, rms_m, temperature}
"""

import json
import logging
import time
from typing import Any, Optional

import redis

from app.config import settings
from app.database import redis_manager

logger = logging.getLogger(__name__)

# Redis key prefix for the data queue
QUEUE_KEY_PREFIX = "mqtt:queue:"
# Redis key prefix for the sequence counter
SEQ_KEY_PREFIX = "mqtt:seq:"


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

    def _get_queue_max_len(self) -> int:
        """Get the configured maximum queue length."""
        return settings.patrol_queue_length

    def _get_next_sequence(self, sn: str) -> int:
        """Atomically increment and return the sequence number for the given SN."""
        seq_key = f"{SEQ_KEY_PREFIX}{sn}"
        # INCR returns the new value after increment; starts at 1 on first call
        return self._client.incr(seq_key)  # type: ignore[union-attr]

    def push_rms_data(self, sn: str, rms_m: float, temperature: float) -> bool:
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
            queue_max_len = self._get_queue_max_len()

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

    def get_queue(self, sn: str, start: int = 0, end: Optional[int] = None) -> list:
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
            end = self._get_queue_max_len() - 1

        try:
            queue_key = f"{QUEUE_KEY_PREFIX}{sn}"
            elements = self._client.lrange(queue_key, start, end)  # type: ignore[union-attr]
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

import logging
from typing import Optional
import redis

logger = logging.getLogger(__name__)

class RedisManager:
    """Manager for Redis connections"""

    def __init__(self):
        self.client: Optional[redis.Redis] = None

    def init(self, redis_url: str) -> None:
        """Initialize Redis connection"""
        try:
            self.client = redis.from_url(redis_url, decode_responses=True)
            self.health_check()
            # logger.info("Redis connection initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
            raise

    def close(self) -> None:
        """Close Redis connection"""
        if self.client:
            self.client.close()
            logger.info("Redis connection closed")

    def health_check(self) -> bool:
        """Check Redis connection health"""
        try:
            if self.client:
                self.client.ping()
                return True
            return False
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False

    def get_client(self) -> redis.Redis:
        """Get Redis client"""
        if not self.client:
            raise RuntimeError("Redis not initialized. Call init() first.")
        return self.client

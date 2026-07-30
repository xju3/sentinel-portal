import logging
from typing import Optional
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)

class MinIOManager:
    """Manager for MinIO connections"""

    def __init__(self):
        self.client: Optional[Minio] = None
        self._bucket: str = ""

    def init(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool = False,
        bucket: str = "fft",
    ) -> None:
        """Initialize MinIO connection"""
        try:
            self._bucket = bucket
            self.client = Minio(
                endpoint=endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure,
            )
            self.health_check()
            self._ensure_bucket()
            # logger.info("MinIO connection initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MinIO: {e}")
            raise

    def close(self) -> None:
        """Close MinIO connection"""
        logger.info("MinIO connection closed")

    def health_check(self) -> bool:
        """Check MinIO connection health"""
        try:
            if self.client:
                self.client.bucket_exists(self._bucket)
                return True
            return False
        except Exception as e:
            logger.error(f"MinIO health check failed: {e}")
            return False

    def _ensure_bucket(self) -> None:
        """Ensure the default bucket exists, create if not"""
        try:
            if self.client:
                if not self.client.bucket_exists(self._bucket):
                    self.client.make_bucket(self._bucket)
                    logger.info(f"Created MinIO bucket: {self._bucket}")
        except S3Error as e:
            logger.error(f"Error managing MinIO bucket: {e}")

    def get_client(self) -> Minio:
        """Get MinIO client"""
        if not self.client:
            raise RuntimeError("MinIO not initialized. Call init() first.")
        return self.client

    @property
    def bucket_name(self) -> str:
        """Return the configured object bucket."""
        return self._bucket or "fft"

    def get_presigned_url(self, file_url: str, expires_hours: int = 24, extra_query_params: dict = None) -> str:
        """Convert a public MinIO URL to a presigned GET URL."""
        from urllib.parse import urlparse
        from datetime import timedelta
        try:
            client = self.get_client()
            parsed_url = urlparse(file_url)
            path_parts = parsed_url.path.lstrip("/").split("/", 1)
            if len(path_parts) == 2:
                bucket_name, object_name = path_parts
                return client.presigned_get_object(
                    bucket_name,
                    object_name,
                    expires=timedelta(hours=expires_hours),
                    extra_query_params=extra_query_params
                )
        except Exception as e:
            logger.warning(f"Failed to generate presigned URL for {file_url}: {e}")
        return file_url

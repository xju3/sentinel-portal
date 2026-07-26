import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

class Settings(BaseSettings):
    app_name: str = "PersistenceService"
    env: str = os.getenv("ENV", "development")
    log_level: str = os.getenv("LOG_LEVEL", "DEBUG")

    mysql_url: str = os.getenv(
        "MYSQL_URL",
        "mysql+aiomysql://root:Stl123456@192.168.3.189:3306/platform?charset=utf8mb4",
    )

    redis_url: str = os.getenv("REDIS_URL", "redis://:Stl123456@192.168.3.189:6379/0")

    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "192.168.3.189:9000")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    minio_secure: bool = str(os.getenv("MINIO_SECURE", "False")).lower() in ("true", "1", "yes")
    minio_bucket: str = os.getenv("MINIO_BUCKET", "fft")
    
    influx_url: str = os.getenv("INFLUX_URL", "http://192.168.3.189:8086")
    influx_token: str = os.getenv("INFLUX_TOKEN", "my-super-secret-auth-token")
    influx_org: str = os.getenv("INFLUX_ORG", "my-org")
    influx_bucket: str = os.getenv("INFLUX_BUCKET", "vibration_data")

    # Stream Worker 配置
    stream_worker_count: int = int(os.getenv("STREAM_WORKER_COUNT", "3"))
    stream_worker_batch_size: int = int(os.getenv("STREAM_WORKER_BATCH_SIZE", "5"))
    stream_maxlen: int = int(os.getenv("STREAM_MAXLEN", "10000"))
    stream_block_ms: int = int(os.getenv("STREAM_BLOCK_MS", "2000"))

    model_config = SettingsConfigDict(
        env_file=(Path.home() / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()

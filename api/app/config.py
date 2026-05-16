from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""
    
    # Application Settings
    app_name: str = "Sensor Portal API"
    app_version: str = "1.0.0"
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    api_prefix: str = "/api/v1"
    cors_origins: List[str] = ["*"]
    
    # MySQL Database
    mysql_url: str = "mysql+aiomysql://pl@pl@sH123@139.9.50.7:3306/platform"
    
    # Redis
    redis_url: str = "redis://139.9.50.7:6379/0"
    
    # InfluxDB
    influx_url: str = "http://139.9.50.7:8086"
    influx_token: str = "MuKqZ3VckkTIM3q4Gj_4TYEoYI-OYLRJueKWQPDPOsQZzHnjKHC56GXgrUKd3vZiGhATJ4EnhWsMSuumdVzaCw=="
    influx_org: str = "myorg"
    influx_bucket: str = "sentinel-accel-raw-data"
    
    # MinIO
    minio_endpoint: str = "139.9.50.7:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket: str = "sensors"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
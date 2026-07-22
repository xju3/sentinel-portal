from pathlib import Path
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

    # JWT
    jwt_secret_key: str = "change-this-secret-in-production"
    jwt_access_token_expires_minutes: int = 1440

    # MySQL Database
    mysql_url: str = "mysql+aiomysql://db_user_name:db_user_password@host_name_or_ip_address:3306/database_name"

    # Redis
    redis_url: str = "redis://host_name_or_ip_address:6379/0"

    # InfluxDB
    influx_url: str = "http://host_name_or_ip_address:8086"
    influx_token: str = "your_influxdb_token"
    influx_org: str = "myorg"
    influx_bucket: str = "sentinel-accel-raw-data"

    # MinIO
    minio_endpoint: str = "host_name_or_ip_address:9000"
    minio_access_key: str = "your_minio_access_key"
    minio_secret_key: str = "your_minio_secret_key"
    minio_secure: bool = False
    minio_bucket: str = "fft"

    # MQTT Configuration
    mqtt_host: str = "host_name_or_ip_address"
    mqtt_port: int = 1883
    mqtt_topic: str = "sentinel"
    mqtt_username: str = "your_mqtt_username"
    mqtt_password: str = "your_mqtt_password"
    mqtt_client_id: str = "sentinel-api-client"
    mqtt_client_id_unique: bool = True
    mqtt_protocol_version: str = "3.1.1"

    # wx settings
    wx_app_id: str = "your wx app id"
    wx_app_secret: str = "your wx app secret"
    wx_token: str = "your wx token"
    wx_encoding_aes_key: str = ""

    # Queue Configuration
    patrol_queue_length: int = 72

    model_config = SettingsConfigDict(
        env_file=(Path.home() / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

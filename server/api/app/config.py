from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict
from pub.utils.redis_url import redis_url_with_db


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
    stream_redis_db: int = 11

    @property
    def stream_redis_url(self) -> str:
        """Redis used only for the persistence/diagnosis data pipeline."""
        return redis_url_with_db(self.redis_url, self.stream_redis_db)

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
    wx_oauth_api_base_url: str = "https://api.weixin.qq.com"
    wx_oauth_authorize_url: str = "https://open.weixin.qq.com/connect/oauth2/authorize"
    wx_diagnosis_oauth_scope: str = "snsapi_base"
    wx_diagnosis_cookie_name: str = "wx_diagnosis_access"
    wx_diagnosis_cookie_ttl_seconds: int = 900
    wx_diagnosis_state_ttl_seconds: int = 600
    wx_diagnosis_cookie_secure: bool = True
    wx_diagnosis_callback_url: str | None = (
        "https://langhu.ai/api/v1/wx/diagnosis/callback"
    )

    # Queue Configuration
    patrol_queue_length: int = 72

    # Registration Email
    email_account: str = ""
    email_passwd: str = ""
    email_server: str = ""
    email_port: int = 587
    email_use_tls: bool = True
    email_tls_verify: bool = True
    portal_base_url: str = "https://langhu.ai"
    portal_login_url: str = "https://portal.api-server.icu"
    password_setup_token_expires_minutes: int = 1440

    model_config = SettingsConfigDict(
        env_file=(Path.home() / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

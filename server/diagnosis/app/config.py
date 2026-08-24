from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pub.utils.redis_url import redis_url_with_db

class Settings(BaseSettings):
    mysql_url: str = "mysql+aiomysql://db_user_name:db_user_password@host_name_or_ip_address:3306/database_name"
    redis_url: str = "redis://host_name_or_ip_address:6379/0"
    stream_redis_db: int = 11

    @property
    def stream_redis_url(self) -> str:
        return redis_url_with_db(self.redis_url, self.stream_redis_db)
    influx_url: str = "http://host_name_or_ip_address:8086"
    influx_token: str = "your_influxdb_token"
    influx_org: str = "myorg"
    influx_bucket: str = "sentinel-accel-raw-data"
    debug: bool = False
    
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
    mqtt_client_id: str = "sentinel-dia-client"
    mqtt_client_id_unique: bool = True
    mqtt_protocol_version: str = "3.1.1"
    mqtt_notification_topic: str = "sentinel/notification/wechat"
    mqtt_publish_timeout_seconds: float = 5.0
    notification_event_schema_version: int = 2

    # Bearing envelope-feature diagnosis. These are centralized server policy
    # thresholds; changing them does not require a firmware update.
    bearing_frequency_tolerance_ratio: float = 0.02
    bearing_frequency_tolerance_bins: float = 2.0
    bearing_attention_snr_db: float = 6.0
    bearing_abnormal_snr_db: float = 10.0
    bearing_warning_snr_db: float = 15.0
    bearing_critical_snr_db: float = 20.0
    model_config = SettingsConfigDict(
        env_file=("../api/.env", "../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sentinel Notification Service"
    app_version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 3013
    debug: bool = False

    mysql_url: str = "mysql+aiomysql://db_user_name:db_user_password@host_name_or_ip_address:3306/database_name"
    redis_url: str = "redis://host_name_or_ip_address:6379/0"

    mqtt_host: str = "host_name_or_ip_address"
    mqtt_port: int = 1883
    mqtt_username: str = "your_mqtt_username"
    mqtt_password: str = "your_mqtt_password"
    mqtt_notification_topic: str = "sentinel/notification/wechat"
    mqtt_notification_client_id: str = "sentinel-notification-client"
    mqtt_keepalive_seconds: int = 60

    wx_app_id: str = "your wx app id"
    wx_app_secret: str = "your wx app secret"
    wx_template_id: str = "gkcCWWRQrMMvypWKQypnfcA3dlU4CM3m9uhzmxKe6KE"
    wx_template_url: str | None = (
        "https://langhu.ai/api/v1/wx/diagnosis/entry"
    )

    notification_timezone: str = "Asia/Shanghai"
    notification_delivery_max_attempts: int = 3
    notification_delivery_retry_seconds: float = 30.0
    bearing_notification_confirmation_count: int = 2
    bearing_notification_window_hours: float = 3.0
    bearing_notification_immediate_level: int = 3

    model_config = SettingsConfigDict(
        env_file=(
            "../api/.env",
            "../../.env",
            Path.home() / ".env",
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

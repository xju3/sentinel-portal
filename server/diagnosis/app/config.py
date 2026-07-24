from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    mysql_url: str = "mysql+aiomysql://db_user_name:db_user_password@host_name_or_ip_address:3306/database_name"
    redis_url: str = "redis://host_name_or_ip_address:6379/0"
    influx_url: str = "http://host_name_or_ip_address:8086"
    influx_token: str = "your_influxdb_token"
    influx_org: str = "myorg"
    influx_bucket: str = "sentinel-accel-raw-data"
    debug: bool = False

    model_config = SettingsConfigDict(
        env_file=("../api/.env", "../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()

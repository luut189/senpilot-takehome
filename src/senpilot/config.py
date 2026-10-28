from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    resend_api_key: SecretStr = SecretStr("")
    resend_webhook_secret: SecretStr = SecretStr("")
    email_from: str = ""
    database_path: Path = Path("data/jobs.sqlite3")
    temp_root: Path = Path("data/tmp")
    max_files: int = Field(10, ge=1, le=10)
    navigation_timeout: int = Field(60, ge=1, le=180)
    download_timeout: int = Field(60, ge=1, le=300)
    job_timeout: int = Field(1200, ge=1, le=3600)
    max_file_bytes: int = Field(25_000_000, ge=1)
    max_total_bytes: int = Field(100_000_000, ge=1)
    max_zip_bytes: int = Field(25_000_000, ge=1)
    max_email_bytes: int = Field(35_000_000, ge=1024, le=35_000_000)
    queue_capacity: int = Field(100, ge=1, le=1000)
    provider_timeout: int = Field(10, ge=1, le=60)
    shutdown_timeout: int = Field(30, ge=1, le=120)
    chromium_channel: str = "chromium"
    headless: bool = True

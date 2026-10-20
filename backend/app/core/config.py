from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    browser_delivery_enabled: bool = False
    weather_freshness_minutes: int = Field(default=180, ge=1, le=10080)
    weather_ingestion_enabled: bool = False
    weather_feed_url: str | None = None
    weather_feed_source: str = "configured-feed"
    weather_feed_synthetic: bool = True
    weather_feed_token: SecretStr | None = None
    weather_poll_seconds: int = Field(default=900, ge=10)
    weather_retry_attempts: int = Field(default=3, ge=1, le=10)
    weather_timeout_seconds: int = Field(default=20, ge=1, le=120)
    synthetic_model_dir: Path = Field(default=BACKEND_DIR.parent / "ml/artifacts/synthetic/v1", validation_alias="SYNTHETIC_MODEL_DIR")
    synthetic_research_dir: Path = Field(
        default=BACKEND_DIR.parent / "ml/artifacts/synthetic/v3", validation_alias="SYNTHETIC_RESEARCH_DIR",
    )
    synthetic_demo_enabled: bool = Field(default=False, validation_alias="SYNTHETIC_DEMO_ENABLED")
    research_model_dir: Path = Field(
        default=BACKEND_DIR.parent / "ml" / "artifacts", validation_alias="RESEARCH_MODEL_DIR",
    )
    alert_demo_enabled: bool = Field(default=False, validation_alias="ALERT_DEMO_ENABLED")
    alert_ttl_hours: int = Field(
        default=24, ge=1, le=720, validation_alias="ALERT_TTL_HOURS",
    )
    alert_cooldown_hours: int = Field(
        default=6, ge=0, le=720, validation_alias="ALERT_COOLDOWN_HOURS",
    )
    database_url: str = Field(validation_alias="DATABASE_URL")
    jwt_secret_key: SecretStr = Field(
        min_length=32,
        validation_alias="JWT_SECRET_KEY",
    )
    jwt_algorithm: Literal["HS256"] = Field(
        default="HS256",
        validation_alias="JWT_ALGORITHM",
    )
    access_token_expire_minutes: int = Field(
        default=60,
        gt=0,
        le=1440,
        validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        """Use SQLAlchemy's psycopg 3 driver for standard PostgreSQL URLs."""
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()

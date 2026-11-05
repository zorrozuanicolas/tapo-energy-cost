from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, read from environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Time zone of the plugs' owner: hour boundaries and tariff bands are computed in it.
    timezone: str = "America/Montevideo"

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # SQLAlchemy URL of the database. The `+aiosqlite` part picks the async SQLite driver.
    database_url: str = "sqlite+aiosqlite:///data/tapo.db"

    # Folder with tariffs.yaml, holidays.yaml and outlets.yaml (relative to backend/).
    config_dir: Path = Path("../config")

    # Raw power readings older than this many days are deleted; hourly totals are kept.
    raw_retention_days: int = Field(default=60, gt=0)

    # Longest interval between two samples that still counts as continuous. With the planned
    # 10 s polling, 60 s tolerates a few missed polls but not a real outage.
    max_gap_seconds: int = Field(default=60, gt=0)

    # Browser origins allowed to call the API. Only needed in development, when the Vite dev server
    # (another port) calls the API; in production one server serves both. Set as a JSON list.
    cors_origins: list[str] = ["http://localhost:5173"]

    @field_validator("timezone")
    @classmethod
    def _timezone_exists(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown time zone: {value!r}") from exc
        return value


@lru_cache
def get_settings() -> Settings:
    """Build the settings once, on first use, and reuse them afterwards."""
    return Settings()

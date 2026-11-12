from functools import lru_cache
from pathlib import Path
from typing import Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# About three years: with a few plugs that is tens of thousands of rows, built in memory.
MAX_SEED_DAYS = 1100


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

    # Seconds between two readings of each plug.
    poll_interval_seconds: int = Field(default=10, gt=0)

    # Fake plugs instead of real ones, so a fresh checkout never touches real hardware.
    tapo_mock: bool = True

    # Turn the poller off to run only the API (for example on a copy of the database).
    poller_enabled: bool = True

    # Days of fake hourly history to create at startup, when there is no energy data yet. 0 turns it
    # off. For demos only, so it needs fake plugs. The cap keeps a typo from building a huge history.
    seed_demo_days: int = Field(default=0, ge=0, le=MAX_SEED_DAYS)

    # Tapo account used to log in to the plugs. The password is a SecretStr: it is hidden
    # in repr(), logs and tracebacks, and read only on purpose with `.get_secret_value()`.
    tapo_username: str = ""
    tapo_password: SecretStr = SecretStr("")

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

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        # One missed poll must not count as an outage, or its energy would be lost.
        if self.max_gap_seconds < 2 * self.poll_interval_seconds:
            raise ValueError(
                f"max_gap_seconds ({self.max_gap_seconds}) must be at least twice "
                f"poll_interval_seconds ({self.poll_interval_seconds})"
            )
        # Fake history in a database that real plugs write to could never be told apart again.
        if self.seed_demo_days > 0 and not self.tapo_mock:
            raise ValueError("SEED_DEMO_DAYS needs TAPO_MOCK=true: demo data must never mix with real readings")
        # Fail at startup, not on the first poll, when real plugs are used without credentials.
        has_credentials = bool(self.tapo_username and self.tapo_password.get_secret_value())
        if self.poller_enabled and not self.tapo_mock and not has_credentials:
            raise ValueError("TAPO_USERNAME and TAPO_PASSWORD are required when TAPO_MOCK is false")
        return self


@lru_cache
def get_settings() -> Settings:
    """Build the settings once, on first use, and reuse them afterwards."""
    return Settings()

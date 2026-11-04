from pathlib import Path

import pytest
from pydantic import ValidationError

from app.settings import Settings, get_settings


def test_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.timezone == "America/Montevideo"
    assert settings.log_level == "INFO"
    assert settings.database_url == "sqlite+aiosqlite:///data/tapo.db"
    assert settings.config_dir == Path("../config")
    assert settings.raw_retention_days == 60
    assert settings.max_gap_seconds == 60


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMEZONE", "Europe/Madrid")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///other.db")
    monkeypatch.setenv("CONFIG_DIR", "/etc/tapo")
    monkeypatch.setenv("RAW_RETENTION_DAYS", "7")
    monkeypatch.setenv("MAX_GAP_SECONDS", "120")

    settings = Settings(_env_file=None)

    assert settings.timezone == "Europe/Madrid"
    assert settings.log_level == "DEBUG"
    assert settings.database_url == "sqlite+aiosqlite:///other.db"
    assert settings.config_dir == Path("/etc/tapo")
    assert settings.raw_retention_days == 7
    assert settings.max_gap_seconds == 120


@pytest.mark.parametrize("days", ["0", "-5"])
def test_non_positive_retention_is_rejected(monkeypatch: pytest.MonkeyPatch, days: str) -> None:
    monkeypatch.setenv("RAW_RETENTION_DAYS", days)

    with pytest.raises(ValidationError, match="raw_retention_days"):
        Settings(_env_file=None)


@pytest.mark.parametrize("seconds", ["0", "-5"])
def test_non_positive_max_gap_is_rejected(monkeypatch: pytest.MonkeyPatch, seconds: str) -> None:
    monkeypatch.setenv("MAX_GAP_SECONDS", seconds)

    with pytest.raises(ValidationError, match="max_gap_seconds"):
        Settings(_env_file=None)


def test_invalid_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "banana")

    with pytest.raises(ValidationError, match="log_level"):
        Settings(_env_file=None)


def test_unknown_timezone_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMEZONE", "Mars/Olympus")

    with pytest.raises(ValidationError, match="unknown time zone"):
        Settings(_env_file=None)


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()

    assert get_settings() is get_settings()

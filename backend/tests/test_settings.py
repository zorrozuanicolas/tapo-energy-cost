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
    assert settings.cors_origins == ["http://localhost:5173"]


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMEZONE", "Europe/Madrid")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///other.db")
    monkeypatch.setenv("CONFIG_DIR", "/etc/tapo")
    monkeypatch.setenv("RAW_RETENTION_DAYS", "7")
    monkeypatch.setenv("MAX_GAP_SECONDS", "120")
    monkeypatch.setenv("CORS_ORIGINS", '["http://a.example", "http://b.example"]')

    settings = Settings(_env_file=None)

    assert settings.timezone == "Europe/Madrid"
    assert settings.log_level == "DEBUG"
    assert settings.database_url == "sqlite+aiosqlite:///other.db"
    assert settings.config_dir == Path("/etc/tapo")
    assert settings.raw_retention_days == 7
    assert settings.max_gap_seconds == 120
    assert settings.cors_origins == ["http://a.example", "http://b.example"]


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


def test_polling_defaults_use_mock_plugs() -> None:
    settings = Settings(_env_file=None)

    assert settings.poll_interval_seconds == 10
    assert settings.tapo_mock is True
    assert settings.poller_enabled is True
    assert settings.tapo_username == ""
    assert settings.tapo_password.get_secret_value() == ""


@pytest.mark.parametrize("seconds", ["0", "-5"])
def test_non_positive_poll_interval_is_rejected(monkeypatch: pytest.MonkeyPatch, seconds: str) -> None:
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", seconds)

    with pytest.raises(ValidationError, match="poll_interval_seconds"):
        Settings(_env_file=None)


def test_max_gap_must_be_at_least_twice_the_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "10")
    monkeypatch.setenv("MAX_GAP_SECONDS", "19")

    with pytest.raises(ValidationError, match="at least twice"):
        Settings(_env_file=None)

    monkeypatch.setenv("MAX_GAP_SECONDS", "20")
    assert Settings(_env_file=None).max_gap_seconds == 20


def test_real_plugs_need_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAPO_MOCK", "false")

    with pytest.raises(ValidationError, match="TAPO_USERNAME and TAPO_PASSWORD"):
        Settings(_env_file=None)

    monkeypatch.setenv("TAPO_USERNAME", "me@example.com")
    with pytest.raises(ValidationError, match="TAPO_USERNAME and TAPO_PASSWORD"):
        Settings(_env_file=None)  # the password is still missing

    monkeypatch.setenv("TAPO_PASSWORD", "secret")
    assert Settings(_env_file=None).tapo_password.get_secret_value() == "secret"


def test_real_plugs_without_credentials_are_fine_when_the_poller_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAPO_MOCK", "false")
    monkeypatch.setenv("POLLER_ENABLED", "false")

    assert Settings(_env_file=None).poller_enabled is False


def test_password_is_hidden_from_repr_and_str(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAPO_PASSWORD", "hunter2")

    settings = Settings(_env_file=None)

    assert "hunter2" not in repr(settings)
    assert "hunter2" not in str(settings)


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

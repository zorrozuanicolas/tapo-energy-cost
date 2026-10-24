import pytest
from pydantic import ValidationError

from app.settings import Settings, get_settings


def test_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.timezone == "America/Montevideo"
    assert settings.log_level == "INFO"


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMEZONE", "Europe/Madrid")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)

    assert settings.timezone == "Europe/Madrid"
    assert settings.log_level == "DEBUG"


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

import asyncio
import io
import logging
from pathlib import Path

import pytest

from app.logs import LOGGER_NAME, configure_logging
from app.main import create_app
from app.settings import Settings

from .conftest import CONFIG_DIR


def test_messages_at_or_above_the_level_are_emitted() -> None:
    stream = io.StringIO()
    configure_logging("INFO", stream)

    log = logging.getLogger("tapo.poller")
    log.debug("too detailed")
    log.info("polling")
    log.warning("unreachable")

    assert stream.getvalue() == "INFO     tapo.poller: polling\nWARNING  tapo.poller: unreachable\n"


def test_messages_do_not_reach_the_root_logger(caplog: pytest.LogCaptureFixture) -> None:
    # Migrations install a handler on the root logger; propagating would print every message twice.
    configure_logging("INFO", io.StringIO())

    logging.getLogger("tapo.poller").info("polling")

    assert caplog.records == []


def test_a_higher_level_hides_the_lower_ones() -> None:
    stream = io.StringIO()
    configure_logging("WARNING", stream)

    logging.getLogger("tapo.poller").info("polling")

    assert stream.getvalue() == ""


def test_configuring_twice_does_not_repeat_messages() -> None:
    first, second = io.StringIO(), io.StringIO()
    configure_logging("INFO", first)
    configure_logging("INFO", second)

    logging.getLogger("tapo.poller").info("polling")

    assert first.getvalue() == ""
    assert second.getvalue().count("polling") == 1


def test_the_app_applies_the_log_level_setting(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'logs.db').as_posix()}",
        config_dir=CONFIG_DIR,
        poller_enabled=False,
        log_level="ERROR",
    )

    async def main() -> int:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            return logging.getLogger(LOGGER_NAME).level

    assert asyncio.run(main()) == logging.ERROR

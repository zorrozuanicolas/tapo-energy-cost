import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

# The real configuration shipped with the repository: <repo>/config
CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture(autouse=True)
def restore_app_logger() -> Iterator[None]:
    """Undo `configure_logging` after each test.

    Starting the app configures the `tapo` logger (own handler, no propagation). Left in place, it would hide
    the app's messages from `caplog` in later tests.
    """
    logger = logging.getLogger("tapo")
    handlers, level, propagate = list(logger.handlers), logger.level, logger.propagate
    yield
    logger.handlers[:] = handlers
    logger.setLevel(level)
    logger.propagate = propagate

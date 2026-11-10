"""Logging setup for the app's own loggers."""

import logging
from typing import TextIO

# The parent of `tapo.poller`, `tapo.supervisor` and any other logger of the app.
LOGGER_NAME = "tapo"

_handler: logging.Handler | None = None


def configure_logging(level: str, stream: TextIO | None = None) -> None:
    """Make the app's loggers emit messages of `level` and above (to stderr, or to `stream`).

    Only the `tapo` loggers are touched: uvicorn and alembic keep their own setup. Calling it again
    replaces the handler instead of adding a second one, so messages are never printed twice.
    Records do not propagate to the root logger: running the migrations installs a handler there
    (alembic.ini), which would print every message a second time.
    """
    global _handler
    logger = logging.getLogger(LOGGER_NAME)
    if _handler is not None:
        logger.removeHandler(_handler)
    _handler = logging.StreamHandler(stream)
    _handler.setFormatter(logging.Formatter("%(levelname)-8s %(name)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(level)
    logger.propagate = False

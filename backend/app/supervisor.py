"""Keeps a background task alive."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

log = logging.getLogger("tapo.supervisor")


async def supervise(name: str, factory: Callable[[], Awaitable[None]], restart_delay: float = 5.0) -> None:
    """Run `factory()` forever: when it fails or returns, log it, wait, and start it again.

    The tasks it supervises are meant never to end, so even a normal return is a problem worth
    restarting. Cancelling `supervise` stops everything (CancelledError is not caught here).
    """
    while True:
        try:
            await factory()
        except Exception:
            log.exception("Task '%s' crashed; restarting in %gs", name, restart_delay)
        else:
            log.warning("Task '%s' ended unexpectedly; restarting in %gs", name, restart_delay)
        await asyncio.sleep(restart_delay)

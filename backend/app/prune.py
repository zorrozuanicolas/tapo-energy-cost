"""Deleting raw readings that are older than the retention period."""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .db import Reading, utcnow
from .settings import Settings

log = logging.getLogger("tapo.prune")

PRUNE_INTERVAL_SECONDS = 6 * 3600


async def prune_readings(
    session_factory: async_sessionmaker[AsyncSession], retention_days: int, now: datetime
) -> int:
    """Delete the readings older than `retention_days`. Returns how many were deleted.

    Only raw readings go. The hourly energy is kept forever, so history and costs do not change.
    """
    cutoff = now - timedelta(days=retention_days)
    async with session_factory() as session:
        result = cast(CursorResult[Any], await session.execute(delete(Reading).where(Reading.ts < cutoff)))
        await session.commit()
    return result.rowcount


async def prune_loop(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    clock: Callable[[], datetime] = utcnow,
) -> None:
    """Prune now and then, forever. Meant to run under `supervise`, which restarts it after an error."""
    while True:
        deleted = await prune_readings(session_factory, settings.raw_retention_days, clock())
        if deleted:
            log.info("Pruned %d raw reading(s) older than %d days", deleted, settings.raw_retention_days)
        await asyncio.sleep(PRUNE_INTERVAL_SECONDS)

"""Filling the hourly energy from the plugs' own history.

A P110 keeps about a week of hourly energy, in whole Wh. Importing it gives the app data from before
its first start, and heals the holes left by outages (a Pi reboot, a Wi-Fi drop).
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from sqlalchemy import CursorResult
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .clients import OutletClient
from .db import HourlyEnergy, utcnow
from .energy import hour_floor
from .outlets import OutletInfo

log = logging.getLogger("tapo.backfill")

BACKFILL_INTERVAL_SECONDS = 6 * 3600
# Longest the history of one plug may take, so a stuck plug cannot hold up the others.
BACKFILL_TIMEOUT_SECONDS = 30.0
# A plug answers at most 8 days at a time (both ends included): today and the 7 days before it.
HISTORY_DAYS = 7

FULL_HOUR_SECONDS = 3600

# An hour the poller covered for at least this long (90%) is trusted over the plug's whole-Wh figure.
MIN_TRUSTED_SECONDS = 3240


async def store_device_hours(
    session_factory: async_sessionmaker[AsyncSession],
    outlet_id: int,
    hours: list[tuple[datetime, float]],
    now: datetime,
) -> int:
    """Store (UTC hour start, Wh) pairs from a plug. Returns how many rows were written.

    - Zeros before the first non-zero hour mean "the plug had no history yet", not real zero
      consumption, so they are skipped.
    - The current hour is skipped: it is still in progress and belongs to the poller.
    - An hour with no row is inserted. An hour the poller measured is replaced only when the poller
      covered less than `MIN_TRUSTED_SECONDS` of it, because then the plug's total is the better figure.
      Running this twice changes nothing: a replaced hour is marked as fully covered.
    """
    current_hour = hour_floor(now)

    # Around a clock change the plug can return two entries with the same start: add them up.
    wh_by_hour: defaultdict[datetime, float] = defaultdict(float)
    for hour_start, wh in hours:
        wh_by_hour[hour_floor(hour_start)] += wh
    ordered = sorted(wh_by_hour.items())

    first = next((i for i, (_, wh) in enumerate(ordered) if wh > 0), None)
    if first is None:
        return 0

    written = 0
    async with session_factory() as session:
        for hour_start, wh in ordered[first:]:
            if hour_start >= current_hour:
                continue
            stmt = insert(HourlyEnergy).values(
                outlet_id=outlet_id, hour_start=hour_start, kwh=wh / 1000.0, seconds_covered=FULL_HOUR_SECONDS
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[HourlyEnergy.outlet_id, HourlyEnergy.hour_start],
                set_={"kwh": stmt.excluded.kwh, "seconds_covered": stmt.excluded.seconds_covered},
                where=HourlyEnergy.seconds_covered < MIN_TRUSTED_SECONDS,
            )
            result = cast(CursorResult[Any], await session.execute(stmt))
            written += result.rowcount
        await session.commit()
    return written


async def backfill_once(
    session_factory: async_sessionmaker[AsyncSession],
    clients: dict[int, OutletClient],
    outlets: list[OutletInfo],
    tz: ZoneInfo,
    now: datetime,
) -> int:
    """Import the history of every plug, one after the other. Returns how many rows were written.

    A plug that fails or does not answer in time is logged and skipped: the next round tries again.
    """
    last_day = now.astimezone(tz).date()
    first_day = last_day - timedelta(days=HISTORY_DAYS)
    total = 0
    for outlet in outlets:
        try:
            hours = await asyncio.wait_for(
                clients[outlet.id].read_hourly_wh(first_day, last_day), BACKFILL_TIMEOUT_SECONDS
            )
            written = await store_device_hours(session_factory, outlet.id, hours, now)
        except Exception as exc:  # noqa: BLE001 - an offline plug is tried again next round
            log.warning("Could not import the history of outlet '%s': %r", outlet.slug, exc)
            continue
        if written:
            log.info("Imported %d hour(s) of history for outlet '%s'", written, outlet.slug)
        total += written
    return total


async def backfill_loop(
    session_factory: async_sessionmaker[AsyncSession],
    clients: dict[int, OutletClient],
    outlets: list[OutletInfo],
    tz: ZoneInfo,
    clock: Callable[[], datetime] = utcnow,
) -> None:
    """Import the plugs' history now and then, forever. Meant to run under `supervise`."""
    while True:
        await backfill_once(session_factory, clients, outlets, tz, clock())
        await asyncio.sleep(BACKFILL_INTERVAL_SECONDS)

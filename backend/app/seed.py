"""Fake hourly history for demos, so the history views have something to show without real plugs."""

import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .billing import BillingConfig
from .db import HourlyEnergy
from .energy import hour_floor
from .outlets import OutletInfo

# The same seed every time, so a demo looks the same on every start.
SEED = 42


def _hour_kwh(index: int, local: datetime, business_day: bool, rng: random.Random) -> float:
    """Energy of one hour for the plug at `index` in the outlet list, at the local time `local`."""
    if index == 0:
        # A fridge: steady, with small variations and the odd harder-working hour.
        value = 0.038 + 0.04 * rng.random()
        return value + (0.05 if rng.random() > 0.97 else 0.0)
    # A desk: busy during working hours, and some evening use on days off.
    hour = local.hour
    if business_day:
        active = 9 <= hour <= 13 or 15 <= hour <= 19 or (hour == 14 and rng.random() > 0.5)
    else:
        active = 11 <= hour <= 22 and rng.random() > 0.45
    return 0.11 + 0.1 * rng.random() if active else 0.004 + 0.004 * rng.random()


async def seed_demo(
    session_factory: async_sessionmaker[AsyncSession],
    outlets: list[OutletInfo],
    days: int,
    tz: ZoneInfo,
    billing: BillingConfig,
    now: datetime,
) -> int:
    """Insert `days` of fake hourly energy, ending at the last completed hour. Returns the rows written.

    It writes nothing if the table already has data, so it can never mix fake hours with real ones.
    """
    if days <= 0:
        return 0
    async with session_factory() as session:
        if (await session.execute(select(HourlyEnergy.outlet_id).limit(1))).first() is not None:
            return 0

    rng = random.Random(SEED)
    end = hour_floor(now)  # the current hour is still going on, so the history stops before it
    rows: list[dict[str, object]] = []
    for offset in range(days * 24, 0, -1):
        hour_start = end - timedelta(hours=offset)
        local = hour_start.astimezone(tz)
        business_day = billing.is_business_day(local.date())
        for index, outlet in enumerate(outlets):
            rows.append(
                {
                    "outlet_id": outlet.id,
                    "hour_start": hour_start,
                    "kwh": _hour_kwh(index, local, business_day, rng),
                    "seconds_covered": 3600,
                }
            )

    async with session_factory() as session:
        # A bulk insert: SQLAlchemy splits a long list into statements that SQLite accepts.
        await session.execute(insert(HourlyEnergy), rows)
        await session.commit()
    return len(rows)

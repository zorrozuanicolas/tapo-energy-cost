"""Turning power samples (W) into energy (kWh) per hour."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .db import HourlyEnergy, Reading


def hour_floor(ts: datetime) -> datetime:
    """Start of the UTC hour that contains `ts`."""
    if ts.tzinfo is None:
        raise ValueError("naive datetime: pass a timezone-aware one")
    return ts.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def split_by_hour(start: datetime, end: datetime) -> list[tuple[datetime, float]]:
    """Split [start, end) into (hour_start, seconds) pieces, one per UTC hour touched."""
    pieces: list[tuple[datetime, float]] = []
    cursor = start
    while cursor < end:
        hour_start = hour_floor(cursor)
        piece_end = min(end, hour_start + timedelta(hours=1))
        pieces.append((hour_start, (piece_end - cursor).total_seconds()))
        cursor = piece_end
    return pieces


def energy_kwh(power_w: float, seconds: float) -> float:
    """Energy of a constant power over a time span: W * s / 3.6e6 = kWh."""
    return power_w * seconds / 3_600_000.0


async def add_energy(
    session: AsyncSession, outlet_id: int, hour_start: datetime, kwh: float, seconds: int
) -> None:
    """Add energy to an hour bucket, creating it if needed (atomic upsert)."""
    stmt = insert(HourlyEnergy).values(
        outlet_id=outlet_id, hour_start=hour_start, kwh=kwh, seconds_covered=seconds
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[HourlyEnergy.outlet_id, HourlyEnergy.hour_start],
        set_={
            "kwh": HourlyEnergy.kwh + stmt.excluded.kwh,
            "seconds_covered": HourlyEnergy.seconds_covered + stmt.excluded.seconds_covered,
        },
    )
    await session.execute(stmt)


async def record_sample(
    session: AsyncSession,
    outlet_id: int,
    ts: datetime,
    power_w: float,
    prev: tuple[datetime, float] | None,
    max_gap_seconds: int,
) -> None:
    """Store a power sample and add the energy used since the previous one.

    The energy of the interval is the average of the two powers times the elapsed time
    (trapezoid rule), split across hours if the interval crosses an hour boundary.
    An interval longer than `max_gap_seconds` is ignored: after an outage we do not know
    what the plug was doing, so it is better to leave a hole than to invent energy.

    The caller commits, so the reading and its energy are saved together or not at all.
    """
    session.add(Reading(outlet_id=outlet_id, ts=ts, power_w=power_w))
    if prev is None:
        return

    prev_ts, prev_power = prev
    gap = (ts - prev_ts).total_seconds()
    if not 0 < gap <= max_gap_seconds:
        return

    average_power = (prev_power + power_w) / 2.0
    elapsed = 0.0
    for hour_start, seconds in split_by_hour(prev_ts, ts):
        # `seconds_covered` is a whole number. Rounding the running total, not each piece,
        # makes the pieces add up to exactly the rounded length of the interval.
        covered = round(elapsed + seconds) - round(elapsed)
        elapsed += seconds
        await add_energy(session, outlet_id, hour_start, energy_kwh(average_power, seconds), covered)

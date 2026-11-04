"""Turning power samples (W) into energy (kWh) per hour."""

from datetime import UTC, datetime, timedelta


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

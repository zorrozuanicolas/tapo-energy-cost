"""Consumption and cost per hour, day or month.

Cost is calculated when it is read, from the stored kWh and the tariff in force at each hour,
so a correction in the tariff or holiday files fixes the whole history. A day or a month is
always the sum of its hourly costs, never total kWh times a single rate.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

Granularity = Literal["hour", "day", "month"]

# Largest range per granularity, so a single request cannot ask for an enormous response.
MAX_HOUR_DAYS = 8
MAX_DAY_DAYS = 62
MAX_MONTHS = 36


class RangeError(ValueError):
    """The requested range is invalid or too large."""


@dataclass(frozen=True)
class Bucket:
    """One slot of the answer: an hour, a day or a month, in local time."""

    start: datetime  # timezone-aware, local
    end: datetime

    @property
    def key(self) -> datetime:
        """The start as an aware UTC datetime. Same shape for every granularity."""
        return self.start.astimezone(UTC)


def _local_midnight(day: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=tz)


def _next_month(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def _hour_buckets(start: date, end: date, tz: ZoneInfo) -> list[Bucket]:
    # Step in UTC: a local day has 23 or 25 hours when the clocks change.
    cursor = _local_midnight(start, tz).astimezone(UTC)
    stop = _local_midnight(end, tz).astimezone(UTC)
    buckets: list[Bucket] = []
    while cursor < stop:
        following = cursor + timedelta(hours=1)
        buckets.append(Bucket(cursor.astimezone(tz), following.astimezone(tz)))
        cursor = following
    return buckets


def _day_buckets(start: date, end: date, tz: ZoneInfo) -> list[Bucket]:
    buckets: list[Bucket] = []
    day = start
    while day < end:
        following = day + timedelta(days=1)
        buckets.append(Bucket(_local_midnight(day, tz), _local_midnight(following, tz)))
        day = following
    return buckets


def _month_buckets(start: date, end: date, tz: ZoneInfo) -> list[Bucket]:
    # Count first, so a huge range is rejected before any bucket is built.
    first = start.replace(day=1)
    months = (end.year - first.year) * 12 + end.month - first.month + (end.day > 1)
    if months > MAX_MONTHS:
        raise RangeError(f"month granularity allows at most {MAX_MONTHS} months")
    buckets: list[Bucket] = []
    month = first
    while month < end:
        following = _next_month(month)
        buckets.append(Bucket(_local_midnight(month, tz), _local_midnight(following, tz)))
        month = following
    return buckets


def make_buckets(granularity: Granularity, start: date, end: date, tz: ZoneInfo) -> list[Bucket]:
    """Empty buckets covering the local dates [start, end). Months snap to whole months."""
    if start >= end:
        raise RangeError("'from' must be earlier than 'to'")

    days = (end - start).days
    if granularity == "hour":
        if days > MAX_HOUR_DAYS:
            raise RangeError(f"hour granularity allows at most {MAX_HOUR_DAYS} days")
        return _hour_buckets(start, end, tz)
    if granularity == "day":
        if days > MAX_DAY_DAYS:
            raise RangeError(f"day granularity allows at most {MAX_DAY_DAYS} days")
        return _day_buckets(start, end, tz)
    return _month_buckets(start, end, tz)

"""Consumption and cost per hour, day or month.

Cost is calculated when it is read, from the stored kWh and the tariff in force at each hour,
so a correction in the tariff or holiday files fixes the whole history. A day or a month is
always the sum of its hourly costs, never total kWh times a single rate.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .billing import BillingConfig
from .db import HourlyEnergy
from .outlets import OutletInfo
from .schemas import (
    BucketOut,
    ConsumptionResponse,
    MissingHolidaysWarning,
    NoTariffWarning,
    OutletOut,
    OutletValue,
    Warning_,
)

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


@dataclass
class _Sums:
    """What has been read into one bucket so far."""

    kwh: dict[int, float] = field(default_factory=dict)
    cost: dict[int, float] = field(default_factory=dict)
    has_data: bool = False


def _bucket_key(granularity: Granularity, hour_start: datetime, tz: ZoneInfo) -> datetime:
    """The `Bucket.key` of the bucket that contains the UTC hour `hour_start`."""
    if granularity == "hour":
        return hour_start
    day = hour_start.astimezone(tz).date()
    if granularity == "month":
        day = day.replace(day=1)
    return _local_midnight(day, tz).astimezone(UTC)


def _bucket_out(
    bucket: Bucket,
    sums: _Sums,
    granularity: Granularity,
    config: BillingConfig,
    outlets: list[OutletInfo],
    now: datetime,
) -> BucketOut:
    band = None
    rate = None
    if granularity == "hour":
        tariff = config.tariff_for(bucket.start.date())
        if tariff is not None:
            band = config.band_for(bucket.start, tariff)
            rate = round(tariff.rate_with_vat(band), 4)
    return BucketOut(
        start=bucket.start,
        end=bucket.end,
        has_data=sums.has_data,
        partial=bucket.start <= now < bucket.end,
        band=band,
        rate_per_kwh=rate,
        outlets={
            o.id: OutletValue(kwh=round(sums.kwh.get(o.id, 0.0), 6), cost=round(sums.cost.get(o.id, 0.0), 4))
            for o in outlets
        },
    )


async def consumption(
    session: AsyncSession,
    config: BillingConfig,
    tz: ZoneInfo,
    outlets: list[OutletInfo],
    granularity: Granularity,
    start: date,
    end: date,
    now: datetime,
) -> ConsumptionResponse:
    """kWh and cost (VAT included) per outlet for each bucket of the local range [start, end).

    Every stored hour is priced on its own, with the tariff and band of that hour, and the
    result is added into the bucket it belongs to. `now` decides which bucket is still in progress.
    """
    buckets = make_buckets(granularity, start, end, tz)
    sums = {bucket.key: _Sums() for bucket in buckets}

    rows = await session.execute(
        select(HourlyEnergy.outlet_id, HourlyEnergy.hour_start, HourlyEnergy.kwh).where(
            HourlyEnergy.outlet_id.in_([o.id for o in outlets]),
            HourlyEnergy.hour_start >= buckets[0].key,
            HourlyEnergy.hour_start < buckets[-1].end.astimezone(UTC),
        )
    )

    first_untariffed: date | None = None
    priced_years: set[int] = set()  # the years that have hours priced with a band, so holidays matter in them
    for outlet_id, hour_start, kwh in rows:
        local = hour_start.astimezone(tz)
        bucket_sums = sums[_bucket_key(granularity, hour_start, tz)]
        bucket_sums.has_data = True
        bucket_sums.kwh[outlet_id] = bucket_sums.kwh.get(outlet_id, 0.0) + kwh
        tariff = config.tariff_for(local.date())
        if tariff is None:
            # The energy is counted, but it cannot be priced.
            if first_untariffed is None or local.date() < first_untariffed:
                first_untariffed = local.date()
            continue
        priced_years.add(local.year)
        price = tariff.rate_with_vat(config.band_for(local, tariff))
        bucket_sums.cost[outlet_id] = bucket_sums.cost.get(outlet_id, 0.0) + kwh * price

    # Only a year with priced hours can be priced wrongly: an empty bucket in a year with no holidays is harmless.
    warnings: list[Warning_] = [
        MissingHolidaysWarning(year=year) for year in sorted(priced_years) if not config.has_holidays_for(year)
    ]
    if first_untariffed is not None:
        warnings.append(NoTariffWarning(since=first_untariffed))

    # Totals add the exact values and are rounded once, so they do not drift from the data.
    return ConsumptionResponse(
        granularity=granularity,
        timezone=str(tz),
        outlets=[OutletOut(id=o.id, slug=o.slug, name=o.name) for o in outlets],
        buckets=[_bucket_out(b, sums[b.key], granularity, config, outlets, now) for b in buckets],
        totals={
            o.id: OutletValue(
                kwh=round(sum(s.kwh.get(o.id, 0.0) for s in sums.values()), 6),
                cost=round(sum(s.cost.get(o.id, 0.0) for s in sums.values()), 4),
            )
            for o in outlets
        },
        warnings=warnings,
    )

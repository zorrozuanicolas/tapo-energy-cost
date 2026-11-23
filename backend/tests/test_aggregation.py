import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.aggregation import (
    MAX_DAY_DAYS,
    MAX_HOUR_DAYS,
    MAX_MONTHS,
    Granularity,
    RangeError,
    consumption,
    make_buckets,
)
from app.billing import BillingConfig, Tariff
from app.db import Base, HourlyEnergy, Outlet
from app.outlets import OutletInfo
from app.schemas import ConsumptionResponse, MissingHolidaysWarning, NoTariffWarning

MONTEVIDEO = ZoneInfo("America/Montevideo")  # UTC-3, no daylight saving time
NEW_YORK = ZoneInfo("America/New_York")  # has daylight saving time


def test_hour_buckets_cover_each_local_day() -> None:
    buckets = make_buckets("hour", date(2026, 1, 1), date(2026, 1, 3), MONTEVIDEO)
    assert len(buckets) == 48
    assert buckets[0].start == datetime(2026, 1, 1, 0, tzinfo=MONTEVIDEO)
    assert buckets[-1].end == datetime(2026, 1, 3, 0, tzinfo=MONTEVIDEO)
    assert all(b.end - b.start == timedelta(hours=1) for b in buckets)


def test_local_midnight_is_three_in_the_morning_utc_in_montevideo() -> None:
    first = make_buckets("hour", date(2026, 1, 1), date(2026, 1, 2), MONTEVIDEO)[0]
    assert first.key == datetime(2026, 1, 1, 3, tzinfo=UTC)


def test_day_buckets_are_consecutive() -> None:
    buckets = make_buckets("day", date(2026, 1, 30), date(2026, 2, 2), MONTEVIDEO)
    assert [b.start.date() for b in buckets] == [date(2026, 1, 30), date(2026, 1, 31), date(2026, 2, 1)]
    assert all(a.end == b.start for a, b in zip(buckets, buckets[1:], strict=False))


def test_month_buckets_snap_to_whole_months() -> None:
    buckets = make_buckets("month", date(2026, 1, 15), date(2026, 3, 2), MONTEVIDEO)
    assert [b.start.date() for b in buckets] == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]
    assert buckets[-1].end.date() == date(2026, 4, 1)


def test_month_buckets_exclude_the_month_that_starts_on_end() -> None:
    buckets = make_buckets("month", date(2026, 1, 1), date(2026, 3, 1), MONTEVIDEO)
    assert [b.start.month for b in buckets] == [1, 2]


def test_month_buckets_cross_a_year_boundary() -> None:
    buckets = make_buckets("month", date(2026, 11, 1), date(2027, 2, 1), MONTEVIDEO)
    assert [(b.start.year, b.start.month) for b in buckets] == [(2026, 11), (2026, 12), (2027, 1)]


def test_hour_buckets_have_23_hours_when_the_clocks_go_forward() -> None:
    buckets = make_buckets("hour", date(2026, 3, 8), date(2026, 3, 9), NEW_YORK)
    assert len(buckets) == 23


def test_hour_buckets_have_25_hours_when_the_clocks_go_back() -> None:
    buckets = make_buckets("hour", date(2026, 11, 1), date(2026, 11, 2), NEW_YORK)
    assert len(buckets) == 25
    assert len({b.key for b in buckets}) == 25  # no two buckets share a UTC start


def test_start_must_be_before_end() -> None:
    with pytest.raises(RangeError):
        make_buckets("day", date(2026, 1, 2), date(2026, 1, 2), MONTEVIDEO)
    with pytest.raises(RangeError):
        make_buckets("day", date(2026, 1, 3), date(2026, 1, 2), MONTEVIDEO)


def test_ranges_at_the_limit_are_accepted_and_beyond_it_rejected() -> None:
    start = date(2026, 1, 1)
    assert make_buckets("hour", start, start + timedelta(days=MAX_HOUR_DAYS), MONTEVIDEO)
    with pytest.raises(RangeError):
        make_buckets("hour", start, start + timedelta(days=MAX_HOUR_DAYS + 1), MONTEVIDEO)

    assert make_buckets("day", start, start + timedelta(days=MAX_DAY_DAYS), MONTEVIDEO)
    with pytest.raises(RangeError):
        make_buckets("day", start, start + timedelta(days=MAX_DAY_DAYS + 1), MONTEVIDEO)

    assert len(make_buckets("month", start, date(2029, 1, 1), MONTEVIDEO)) == MAX_MONTHS
    with pytest.raises(RangeError):
        make_buckets("month", start, date(2029, 1, 2), MONTEVIDEO)


# --- consumption: cost calculation -------------------------------------------------------------

A = OutletInfo(id=1, slug="a", name="A", ip="10.0.0.1", model="p110")
B = OutletInfo(id=2, slug="b", name="B", ip="10.0.0.2", model="p110")

# Round numbers on purpose (no VAT): valle 1, llano 2, punta 10 pesos per kWh, punta 17:00-21:00.
TARIFF = Tariff(date(2026, 1, 1), vat=1.0, peak_start=17, peak_end=21, rates={"valle": 1, "llano": 2, "punta": 10})
# 2026-01-05 is a Monday, 2026-01-06 is a Tuesday declared as a holiday, 2026-01-03 is a Saturday.
CONFIG = BillingConfig(tariffs=[TARIFF], holidays={2026: {date(2026, 1, 6): "Holiday"}})
NOW = datetime(2026, 6, 1, tzinfo=UTC)


def at(day: int, hour: int, month: int = 1, year: int = 2026) -> datetime:
    """A local Montevideo hour as the aware UTC datetime that is stored."""
    return datetime(year, month, day, hour, tzinfo=MONTEVIDEO).astimezone(UTC)


def run_consumption(
    tmp_path: Path,
    rows: list[tuple[int, datetime, float]],
    granularity: Granularity,
    start: date,
    end: date,
    *,
    config: BillingConfig = CONFIG,
    outlets: list[OutletInfo] | None = None,
    now: datetime = NOW,
) -> ConsumptionResponse:
    """Store `rows` (outlet id, hour, kWh) in a throwaway database and read them back."""

    async def main() -> ConsumptionResponse:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/{uuid4().hex}.db")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                session.add_all([Outlet(id=o.id, slug=o.slug, name=o.name, ip=o.ip) for o in (A, B)])
                await session.commit()
                session.add_all(
                    HourlyEnergy(outlet_id=oid, hour_start=hour, kwh=kwh, seconds_covered=3600)
                    for oid, hour, kwh in rows
                )
                await session.commit()
                return await consumption(session, config, MONTEVIDEO, outlets or [A], granularity, start, end, now)
        finally:
            await engine.dispose()

    return asyncio.run(main())


def test_each_hour_is_priced_with_its_own_band(tmp_path: Path) -> None:
    rows = [(1, at(5, 3), 1.0), (1, at(5, 10), 1.0), (1, at(5, 18), 1.0)]
    result = run_consumption(tmp_path, rows, "hour", date(2026, 1, 5), date(2026, 1, 6))

    valle, llano, punta = result.buckets[3], result.buckets[10], result.buckets[18]
    assert (valle.band, valle.rate_per_kwh, valle.outlets[1].cost) == ("valle", 1, 1)
    assert (llano.band, llano.rate_per_kwh, llano.outlets[1].cost) == ("llano", 2, 2)
    assert (punta.band, punta.rate_per_kwh, punta.outlets[1].cost) == ("punta", 10, 10)
    assert result.totals[1].cost == pytest.approx(13)


def test_a_day_is_the_sum_of_its_hourly_costs(tmp_path: Path) -> None:
    rows = [(1, at(5, 3), 2.0), (1, at(5, 18), 1.0)]
    day = run_consumption(tmp_path, rows, "day", date(2026, 1, 5), date(2026, 1, 6)).buckets[0]

    # 2 kWh x 1 + 1 kWh x 10. Total kWh times any single rate would give 3, 6 or 30.
    assert day.outlets[1].kwh == pytest.approx(3)
    assert day.outlets[1].cost == pytest.approx(12)
    assert day.band is None and day.rate_per_kwh is None


def test_punta_hours_are_llano_on_holidays_and_weekends(tmp_path: Path) -> None:
    rows = [(1, at(6, 18), 1.0), (1, at(3, 18), 1.0)]  # holiday Tuesday, ordinary Saturday
    holiday = run_consumption(tmp_path, rows, "day", date(2026, 1, 6), date(2026, 1, 7))
    weekend = run_consumption(tmp_path, rows, "day", date(2026, 1, 3), date(2026, 1, 4))
    assert holiday.totals[1].cost == pytest.approx(2)
    assert weekend.totals[1].cost == pytest.approx(2)


def test_months_follow_local_time_not_utc(tmp_path: Path) -> None:
    # 23:00 on 31 January in Montevideo is already 1 February in UTC.
    rows = [(1, at(31, 23), 1.0), (1, at(1, 0, month=2), 1.0)]
    result = run_consumption(tmp_path, rows, "month", date(2026, 1, 1), date(2026, 3, 1))

    january, february = result.buckets
    assert january.outlets[1].kwh == pytest.approx(1)
    assert february.outlets[1].kwh == pytest.approx(1)


def test_a_tariff_change_prices_each_side_with_its_own_tariff(tmp_path: Path) -> None:
    newer = Tariff(
        date(2026, 1, 10), vat=1.0, peak_start=17, peak_end=21, rates={"valle": 2, "llano": 4, "punta": 20}
    )
    config = BillingConfig(tariffs=[TARIFF, newer], holidays={2026: {}})
    rows = [(1, at(9, 10), 1.0), (1, at(10, 10), 1.0)]
    result = run_consumption(tmp_path, rows, "day", date(2026, 1, 9), date(2026, 1, 11), config=config)

    assert [b.outlets[1].cost for b in result.buckets] == pytest.approx([2, 4])


def test_vat_is_included_in_the_cost(tmp_path: Path) -> None:
    taxed = Tariff(
        date(2026, 1, 1), vat=1.22, peak_start=17, peak_end=21, rates={"valle": 1, "llano": 2, "punta": 10}
    )
    config = BillingConfig(tariffs=[taxed], holidays={2026: {}})
    rows = [(1, at(5, 10), 1.0)]
    result = run_consumption(tmp_path, rows, "hour", date(2026, 1, 5), date(2026, 1, 6), config=config)

    assert result.buckets[10].rate_per_kwh == pytest.approx(2.44)
    assert result.totals[1].cost == pytest.approx(2.44)


def test_only_the_bucket_that_contains_now_is_partial(tmp_path: Path) -> None:
    now = datetime(2026, 1, 5, 12, tzinfo=MONTEVIDEO)
    result = run_consumption(tmp_path, [], "day", date(2026, 1, 4), date(2026, 1, 7), now=now)
    assert [b.partial for b in result.buckets] == [False, True, False]


def test_buckets_without_data_are_marked_and_zero(tmp_path: Path) -> None:
    result = run_consumption(tmp_path, [(1, at(5, 10), 1.0)], "day", date(2026, 1, 4), date(2026, 1, 7))
    assert [b.has_data for b in result.buckets] == [False, True, False]
    assert result.buckets[0].outlets[1].kwh == 0
    assert result.buckets[0].outlets[1].cost == 0


def test_outlets_are_separate_and_unrequested_ones_are_ignored(tmp_path: Path) -> None:
    rows = [(1, at(5, 10), 1.0), (2, at(5, 10), 3.0)]
    both = run_consumption(tmp_path, rows, "day", date(2026, 1, 5), date(2026, 1, 6), outlets=[A, B])
    only_a = run_consumption(tmp_path, rows, "day", date(2026, 1, 5), date(2026, 1, 6), outlets=[A])

    assert [(o.id, o.slug) for o in both.outlets] == [(1, "a"), (2, "b")]
    assert both.totals[1].kwh == pytest.approx(1)
    assert both.totals[2].kwh == pytest.approx(3)
    assert set(only_a.totals) == {1}


def test_each_year_with_priced_hours_and_no_holidays_produces_a_warning(tmp_path: Path) -> None:
    config = BillingConfig(tariffs=[TARIFF], holidays={2025: {}})
    rows = [(1, at(31, 10, month=12, year=2026), 1.0), (1, at(1, 10, year=2027), 1.0)]
    result = run_consumption(tmp_path, rows, "day", date(2026, 12, 31), date(2027, 1, 2), config=config)
    assert result.warnings == [MissingHolidaysWarning(year=2026), MissingHolidaysWarning(year=2027)]


def test_a_year_without_data_in_the_range_produces_no_warning(tmp_path: Path) -> None:
    # The range reaches into 2027 (no holiday list), but all the data is in 2026.
    config = BillingConfig(tariffs=[TARIFF], holidays={2026: {}})
    rows = [(1, at(30, 10, month=12), 1.0)]
    result = run_consumption(tmp_path, rows, "day", date(2026, 12, 30), date(2027, 1, 3), config=config)
    assert result.warnings == []


def test_hours_that_cannot_be_priced_do_not_ask_for_holidays(tmp_path: Path) -> None:
    config = BillingConfig(tariffs=[TARIFF], holidays={})  # no holidays at all, and no tariff before 2026
    rows = [(1, at(31, 10, month=12, year=2025), 1.0)]
    result = run_consumption(tmp_path, rows, "day", date(2025, 12, 31), date(2026, 1, 1), config=config)
    assert result.warnings == [NoTariffWarning(since=date(2025, 12, 31))]


def test_hours_before_the_first_tariff_count_kwh_but_have_no_cost(tmp_path: Path) -> None:
    config = BillingConfig(tariffs=[TARIFF], holidays={2025: {}, 2026: {}})
    rows = [(1, at(31, 10, month=12, year=2025), 1.0), (1, at(1, 10), 1.0)]
    result = run_consumption(tmp_path, rows, "day", date(2025, 12, 30), date(2026, 1, 3), config=config)

    assert result.totals[1].kwh == pytest.approx(2)
    assert result.totals[1].cost == pytest.approx(2)  # only the priced January hour
    assert result.warnings == [NoTariffWarning(since=date(2025, 12, 31))]

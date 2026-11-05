from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.aggregation import MAX_DAY_DAYS, MAX_HOUR_DAYS, MAX_MONTHS, RangeError, make_buckets

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

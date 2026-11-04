from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.energy import energy_kwh, hour_floor, split_by_hour


def test_hour_floor_truncates_to_the_hour() -> None:
    ts = datetime(2026, 10, 22, 10, 59, 30, 123456, tzinfo=UTC)
    assert hour_floor(ts) == datetime(2026, 10, 22, 10, tzinfo=UTC)


def test_hour_floor_converts_to_utc_first() -> None:
    # 15:45 in UTC+5:30 is 10:15 UTC, so the UTC hour starts at 10:00.
    india = timezone(timedelta(hours=5, minutes=30))
    ts = datetime(2026, 10, 22, 15, 45, tzinfo=india)
    assert hour_floor(ts) == datetime(2026, 10, 22, 10, tzinfo=UTC)


def test_hour_floor_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="naive"):
        hour_floor(datetime(2026, 10, 22, 10, 30))


def test_split_by_hour_inside_one_hour() -> None:
    start = datetime(2026, 10, 22, 10, 10, tzinfo=UTC)
    end = datetime(2026, 10, 22, 10, 40, tzinfo=UTC)
    assert split_by_hour(start, end) == [(datetime(2026, 10, 22, 10, tzinfo=UTC), 1800.0)]


def test_split_by_hour_across_a_boundary() -> None:
    start = datetime(2026, 10, 22, 10, 59, 30, tzinfo=UTC)
    end = datetime(2026, 10, 22, 11, 0, 30, tzinfo=UTC)
    assert split_by_hour(start, end) == [
        (datetime(2026, 10, 22, 10, tzinfo=UTC), 30.0),
        (datetime(2026, 10, 22, 11, tzinfo=UTC), 30.0),
    ]


def test_split_by_hour_across_several_hours() -> None:
    start = datetime(2026, 10, 22, 10, 30, tzinfo=UTC)
    end = datetime(2026, 10, 22, 13, 15, tzinfo=UTC)
    assert split_by_hour(start, end) == [
        (datetime(2026, 10, 22, 10, tzinfo=UTC), 1800.0),
        (datetime(2026, 10, 22, 11, tzinfo=UTC), 3600.0),
        (datetime(2026, 10, 22, 12, tzinfo=UTC), 3600.0),
        (datetime(2026, 10, 22, 13, tzinfo=UTC), 900.0),
    ]


def test_split_by_hour_of_an_empty_interval_is_empty() -> None:
    ts = datetime(2026, 10, 22, 10, 30, tzinfo=UTC)
    assert split_by_hour(ts, ts) == []


def test_energy_of_100_watts_for_one_hour_is_0_1_kwh() -> None:
    assert energy_kwh(100, 3600) == pytest.approx(0.1)


def test_energy_of_zero_watts_is_zero() -> None:
    assert energy_kwh(0, 3600) == 0

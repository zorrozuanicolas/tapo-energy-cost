import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base, HourlyEnergy, Outlet, Reading
from app.energy import energy_kwh, hour_floor, record_sample, split_by_hour

MAX_GAP = 60


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


def run_with_session[T](tmp_path: Path, work: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Create the tables and one outlet (id 1) in a throwaway database, then run `work` on a session."""

    async def main() -> T:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/energy.db")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                session.add(Outlet(id=1, slug="a", name="A", ip="1.1.1.1"))
                await session.commit()
                return await work(session)
        finally:
            await engine.dispose()

    return asyncio.run(main())


async def hourly_rows(session: AsyncSession) -> list[HourlyEnergy]:
    return list((await session.execute(select(HourlyEnergy).order_by(HourlyEnergy.hour_start))).scalars())


async def reading_count(session: AsyncSession) -> int:
    return len((await session.execute(select(Reading))).scalars().all())


def test_first_sample_stores_only_the_reading(tmp_path: Path) -> None:
    async def work(session: AsyncSession) -> tuple[int, list[HourlyEnergy]]:
        await record_sample(session, 1, datetime(2026, 10, 22, 12, 0, tzinfo=UTC), 100.0, None, MAX_GAP)
        await session.commit()
        return await reading_count(session), await hourly_rows(session)

    readings, hourly = run_with_session(tmp_path, work)
    assert readings == 1
    assert hourly == []


def test_energy_is_the_trapezoid_of_the_two_samples(tmp_path: Path) -> None:
    prev = (datetime(2026, 10, 22, 12, 0, tzinfo=UTC), 100.0)

    async def work(session: AsyncSession) -> list[HourlyEnergy]:
        await record_sample(session, 1, datetime(2026, 10, 22, 12, 1, tzinfo=UTC), 200.0, prev, MAX_GAP)
        await session.commit()
        return await hourly_rows(session)

    (row,) = run_with_session(tmp_path, work)
    assert row.hour_start == datetime(2026, 10, 22, 12, tzinfo=UTC)
    assert row.kwh == pytest.approx(150 * 60 / 3_600_000)  # average 150 W for 60 s
    assert row.seconds_covered == 60


def test_energy_is_split_between_two_hours(tmp_path: Path) -> None:
    prev = (datetime(2026, 10, 22, 10, 59, 30, tzinfo=UTC), 100.0)

    async def work(session: AsyncSession) -> list[HourlyEnergy]:
        await record_sample(session, 1, datetime(2026, 10, 22, 11, 0, 30, tzinfo=UTC), 100.0, prev, MAX_GAP)
        await session.commit()
        return await hourly_rows(session)

    rows = run_with_session(tmp_path, work)
    assert [row.hour_start.hour for row in rows] == [10, 11]
    assert [row.seconds_covered for row in rows] == [30, 30]
    assert all(row.kwh == pytest.approx(100 * 30 / 3_600_000) for row in rows)


def test_seconds_covered_adds_up_to_the_rounded_interval(tmp_path: Path) -> None:
    # Two pieces of 0.5 s: rounding each one would give 0 + 0 (or 1 + 1), never the true 1 s.
    prev = (datetime(2026, 10, 22, 10, 59, 59, 500_000, tzinfo=UTC), 100.0)

    async def work(session: AsyncSession) -> list[HourlyEnergy]:
        await record_sample(
            session, 1, datetime(2026, 10, 22, 11, 0, 0, 500_000, tzinfo=UTC), 100.0, prev, MAX_GAP
        )
        await session.commit()
        return await hourly_rows(session)

    rows = run_with_session(tmp_path, work)
    assert sum(row.seconds_covered for row in rows) == 1
    assert sum(row.kwh for row in rows) == pytest.approx(100 * 1 / 3_600_000)


def test_energy_accumulates_in_the_same_hour(tmp_path: Path) -> None:
    t0 = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    t1 = datetime(2026, 10, 22, 12, 0, 30, tzinfo=UTC)
    t2 = datetime(2026, 10, 22, 12, 1, tzinfo=UTC)

    async def work(session: AsyncSession) -> list[HourlyEnergy]:
        await record_sample(session, 1, t1, 60.0, (t0, 60.0), MAX_GAP)
        await record_sample(session, 1, t2, 60.0, (t1, 60.0), MAX_GAP)
        await session.commit()
        return await hourly_rows(session)

    (row,) = run_with_session(tmp_path, work)
    assert row.kwh == pytest.approx(60 * 60 / 3_600_000)
    assert row.seconds_covered == 60


def test_gap_longer_than_the_limit_leaves_a_hole(tmp_path: Path) -> None:
    prev = (datetime(2026, 10, 22, 12, 0, tzinfo=UTC), 500.0)

    async def work(session: AsyncSession) -> tuple[int, list[HourlyEnergy]]:
        await record_sample(session, 1, prev[0] + timedelta(seconds=MAX_GAP + 1), 500.0, prev, MAX_GAP)
        await session.commit()
        return await reading_count(session), await hourly_rows(session)

    readings, hourly = run_with_session(tmp_path, work)
    assert readings == 1  # the raw sample is still stored
    assert hourly == []


def test_gap_equal_to_the_limit_is_integrated(tmp_path: Path) -> None:
    prev = (datetime(2026, 10, 22, 12, 0, tzinfo=UTC), 100.0)

    async def work(session: AsyncSession) -> list[HourlyEnergy]:
        await record_sample(session, 1, prev[0] + timedelta(seconds=MAX_GAP), 100.0, prev, MAX_GAP)
        await session.commit()
        return await hourly_rows(session)

    (row,) = run_with_session(tmp_path, work)
    assert row.seconds_covered == MAX_GAP


@pytest.mark.parametrize("offset_seconds", [0, -30])
def test_a_sample_that_is_not_after_the_previous_adds_no_energy(tmp_path: Path, offset_seconds: int) -> None:
    prev = (datetime(2026, 10, 22, 12, 0, tzinfo=UTC), 100.0)

    async def work(session: AsyncSession) -> list[HourlyEnergy]:
        await record_sample(session, 1, prev[0] + timedelta(seconds=offset_seconds), 100.0, prev, MAX_GAP)
        await session.commit()
        return await hourly_rows(session)

    assert run_with_session(tmp_path, work) == []


def test_record_sample_does_not_commit(tmp_path: Path) -> None:
    prev = (datetime(2026, 10, 22, 12, 0, tzinfo=UTC), 100.0)

    async def work(session: AsyncSession) -> tuple[int, list[HourlyEnergy]]:
        await record_sample(session, 1, datetime(2026, 10, 22, 12, 0, 30, tzinfo=UTC), 100.0, prev, MAX_GAP)
        await session.rollback()
        return await reading_count(session), await hourly_rows(session)

    readings, hourly = run_with_session(tmp_path, work)
    assert readings == 0
    assert hourly == []

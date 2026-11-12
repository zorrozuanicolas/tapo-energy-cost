import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.backfill import MIN_TRUSTED_SECONDS, store_device_hours
from app.db import Base, HourlyEnergy, Outlet

NOW = datetime(2026, 11, 10, 12, 30, tzinfo=UTC)
SessionFactory = async_sessionmaker[AsyncSession]


def hour(hours_ago: int) -> datetime:
    """The start of a whole UTC hour, `hours_ago` hours before the hour that contains NOW."""
    return NOW.replace(minute=0) - timedelta(hours=hours_ago)


def run_with_factory[T](tmp_path: Path, work: Callable[[SessionFactory], Awaitable[T]]) -> T:
    """Create the tables and outlet 1 in a throwaway database, then run `work`."""

    async def main() -> T:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/backfill.db")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                session.add(Outlet(id=1, slug="a", name="A", ip="1.1.1.1"))
                await session.commit()
            return await work(factory)
        finally:
            await engine.dispose()

    return asyncio.run(main())


async def rows(factory: SessionFactory) -> dict[datetime, tuple[float, int]]:
    """Every stored hour as {hour_start: (kwh, seconds_covered)}."""
    async with factory() as session:
        found = (await session.execute(select(HourlyEnergy))).scalars().all()
    return {row.hour_start: (row.kwh, row.seconds_covered) for row in found}


async def measured_by_poller(factory: SessionFactory, hours_ago: int, kwh: float, seconds: int) -> None:
    async with factory() as session:
        session.add(HourlyEnergy(outlet_id=1, hour_start=hour(hours_ago), kwh=kwh, seconds_covered=seconds))
        await session.commit()


def test_new_hours_are_inserted_as_fully_covered(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> tuple[int, dict[datetime, tuple[float, int]]]:
        written = await store_device_hours(factory, 1, [(hour(3), 120.0), (hour(2), 80.0)], NOW)
        return written, await rows(factory)

    written, stored = run_with_factory(tmp_path, work)

    assert written == 2
    assert stored == {hour(3): (0.12, 3600), hour(2): (0.08, 3600)}


def test_zeros_before_the_first_non_zero_hour_are_skipped(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> set[datetime]:
        history = [(hour(5), 0.0), (hour(4), 0.0), (hour(3), 50.0), (hour(2), 0.0), (hour(1), 10.0)]
        await store_device_hours(factory, 1, history, NOW)
        return set(await rows(factory))

    # The zero after the first real hour is real consumption (the plug was off), so it stays.
    assert run_with_factory(tmp_path, work) == {hour(3), hour(2), hour(1)}


def test_a_history_of_only_zeros_stores_nothing(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> tuple[int, dict[datetime, tuple[float, int]]]:
        written = await store_device_hours(factory, 1, [(hour(2), 0.0), (hour(1), 0.0)], NOW)
        return written, await rows(factory)

    assert run_with_factory(tmp_path, work) == (0, {})


def test_the_current_and_later_hours_are_skipped(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> set[datetime]:
        await store_device_hours(factory, 1, [(hour(1), 5.0), (hour(0), 7.0), (hour(-1), 9.0)], NOW)
        return set(await rows(factory))

    assert run_with_factory(tmp_path, work) == {hour(1)}


def test_a_well_covered_hour_is_left_alone(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> tuple[int, dict[datetime, tuple[float, int]]]:
        await measured_by_poller(factory, 2, kwh=0.1234, seconds=MIN_TRUSTED_SECONDS)
        written = await store_device_hours(factory, 1, [(hour(2), 999.0)], NOW)
        return written, await rows(factory)

    written, stored = run_with_factory(tmp_path, work)

    assert written == 0
    assert stored == {hour(2): (0.1234, MIN_TRUSTED_SECONDS)}


def test_a_poorly_covered_hour_is_replaced_by_the_plug_total(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> tuple[int, dict[datetime, tuple[float, int]]]:
        await measured_by_poller(factory, 2, kwh=0.01, seconds=MIN_TRUSTED_SECONDS - 1)
        written = await store_device_hours(factory, 1, [(hour(2), 120.0)], NOW)
        return written, await rows(factory)

    written, stored = run_with_factory(tmp_path, work)

    assert written == 1
    assert stored == {hour(2): (0.12, 3600)}


def test_running_twice_changes_nothing_the_second_time(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> tuple[int, int]:
        await measured_by_poller(factory, 2, kwh=0.01, seconds=600)
        history = [(hour(3), 50.0), (hour(2), 120.0)]
        first = await store_device_hours(factory, 1, history, NOW)
        second = await store_device_hours(factory, 1, history, NOW)
        return first, second

    assert run_with_factory(tmp_path, work) == (2, 0)


def test_entries_with_the_same_start_are_added_up(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> dict[datetime, tuple[float, int]]:
        # What a clock change can produce: two entries for the same hour.
        await store_device_hours(factory, 1, [(hour(2), 30.0), (hour(2), 20.0)], NOW)
        return await rows(factory)

    assert run_with_factory(tmp_path, work) == {hour(2): (0.05, 3600)}


def test_rejects_a_naive_hour(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> int:
        return await store_device_hours(factory, 1, [(datetime(2026, 11, 10, 8), 5.0)], NOW)

    with pytest.raises(ValueError, match="naive"):
        run_with_factory(tmp_path, work)

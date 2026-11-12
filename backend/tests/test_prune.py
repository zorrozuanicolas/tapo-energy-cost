import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.prune
from app.db import Base, HourlyEnergy, Outlet, Reading
from app.prune import prune_loop, prune_readings
from app.settings import Settings

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
SessionFactory = async_sessionmaker[AsyncSession]


def run_with_factory[T](tmp_path: Path, work: Callable[[SessionFactory], Awaitable[T]]) -> T:
    """Create the tables and outlet 1 in a throwaway database, then run `work`."""

    async def main() -> T:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/prune.db")
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


async def add_readings(factory: SessionFactory, *ages_days: int) -> None:
    async with factory() as session:
        session.add_all(Reading(outlet_id=1, ts=NOW - timedelta(days=age), power_w=10.0) for age in ages_days)
        await session.commit()


async def ages_left(factory: SessionFactory) -> list[int]:
    async with factory() as session:
        stamps = (await session.execute(select(Reading.ts))).scalars().all()
    return sorted((NOW - ts).days for ts in stamps)


def test_old_readings_are_deleted_and_recent_ones_kept(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> tuple[int, list[int]]:
        await add_readings(factory, 91, 90, 89, 0)
        deleted = await prune_readings(factory, retention_days=90, now=NOW)
        return deleted, await ages_left(factory)

    deleted, left = run_with_factory(tmp_path, work)

    assert deleted == 1  # only the 91-day-old one; exactly 90 days is still kept
    assert left == [0, 89, 90]


def test_nothing_to_delete_returns_zero(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> int:
        await add_readings(factory, 1, 2)
        return await prune_readings(factory, retention_days=90, now=NOW)

    assert run_with_factory(tmp_path, work) == 0


def test_hourly_energy_is_never_deleted(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> int:
        async with factory() as session:
            session.add(
                HourlyEnergy(outlet_id=1, hour_start=NOW - timedelta(days=500), kwh=1.0, seconds_covered=3600)
            )
            await session.commit()
        await add_readings(factory, 500)
        await prune_readings(factory, retention_days=90, now=NOW)
        async with factory() as session:
            return len((await session.execute(select(HourlyEnergy))).scalars().all())

    assert run_with_factory(tmp_path, work) == 1


def test_the_loop_prunes_at_start_and_again_after_the_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.prune, "PRUNE_INTERVAL_SECONDS", 0.02)
    settings = Settings(raw_retention_days=90)

    async def work(factory: SessionFactory) -> list[int]:
        await add_readings(factory, 91)
        task = asyncio.create_task(prune_loop(settings, factory, clock=lambda: NOW))
        await asyncio.sleep(0.01)
        first_round = await ages_left(factory)
        await add_readings(factory, 120)  # appears after the first round
        await asyncio.sleep(0.06)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert first_round == []
        return await ages_left(factory)

    assert run_with_factory(tmp_path, work) == []

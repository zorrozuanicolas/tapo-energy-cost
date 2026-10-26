import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base, HourlyEnergy, Outlet, Reading

HOUR = datetime(2026, 10, 26, 14, 0, tzinfo=UTC)


def run_with_session[T](tmp_path: Path, work: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Create the tables in a throwaway database and run `work` with a session on it."""

    async def main() -> T:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/models.db")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                return await work(session)
        finally:
            await engine.dispose()

    return asyncio.run(main())


def test_aware_datetime_round_trips_as_utc(tmp_path: Path) -> None:
    async def work(session: AsyncSession) -> datetime:
        session.add(Outlet(id=1, slug="a", name="A", ip="1.1.1.1"))
        session.add(Reading(outlet_id=1, ts=HOUR, power_w=40.0))
        await session.commit()
        session.expunge_all()
        return (await session.get(Reading, 1)).ts  # type: ignore[union-attr]

    ts = run_with_session(tmp_path, work)

    assert ts == HOUR
    assert ts.tzinfo is UTC


def test_other_time_zone_is_normalised_to_utc(tmp_path: Path) -> None:
    montevideo = timezone(timedelta(hours=-3))

    async def work(session: AsyncSession) -> datetime:
        session.add(Outlet(id=1, slug="a", name="A", ip="1.1.1.1"))
        session.add(Reading(outlet_id=1, ts=datetime(2026, 10, 26, 11, 0, tzinfo=montevideo), power_w=1))
        await session.commit()
        session.expunge_all()
        return (await session.get(Reading, 1)).ts  # type: ignore[union-attr]

    ts = run_with_session(tmp_path, work)

    assert ts == HOUR
    assert ts.tzinfo is UTC


def test_naive_datetime_is_rejected(tmp_path: Path) -> None:
    async def work(session: AsyncSession) -> None:
        session.add(Outlet(id=1, slug="a", name="A", ip="1.1.1.1"))
        session.add(Reading(outlet_id=1, ts=datetime(2026, 10, 26, 14, 0), power_w=1))
        await session.commit()

    with pytest.raises(StatementError, match="naive datetime"):
        run_with_session(tmp_path, work)


def test_duplicate_slug_is_rejected(tmp_path: Path) -> None:
    async def work(session: AsyncSession) -> None:
        session.add(Outlet(slug="a", name="A", ip="1.1.1.1"))
        session.add(Outlet(slug="a", name="Other", ip="2.2.2.2"))
        await session.commit()

    with pytest.raises(IntegrityError):
        run_with_session(tmp_path, work)


def test_hourly_energy_has_one_row_per_outlet_and_hour(tmp_path: Path) -> None:
    async def work(session: AsyncSession) -> None:
        session.add(Outlet(id=1, slug="a", name="A", ip="1.1.1.1"))
        session.add(HourlyEnergy(outlet_id=1, hour_start=HOUR, kwh=0.1, seconds_covered=3600))
        session.add(HourlyEnergy(outlet_id=1, hour_start=HOUR, kwh=0.2, seconds_covered=1800))
        await session.commit()

    with pytest.raises(IntegrityError):
        run_with_session(tmp_path, work)

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.billing import load_billing_config
from app.db import Base, HourlyEnergy, Outlet
from app.outlets import OutletInfo
from app.seed import seed_demo

from .conftest import CONFIG_DIR

TZ = ZoneInfo("America/Montevideo")
BILLING = load_billing_config(CONFIG_DIR)
NOW = datetime(2026, 11, 10, 12, 30, tzinfo=UTC)
SessionFactory = async_sessionmaker[AsyncSession]

FRIDGE = OutletInfo(id=1, slug="fridge", name="Fridge", ip="1.1.1.1", model="p110")
DESK = OutletInfo(id=2, slug="desk", name="Desk", ip="1.1.1.2", model="p110")
OUTLETS = [FRIDGE, DESK]

Rows = dict[tuple[int, datetime], tuple[float, int]]


def run_with_factory[T](tmp_path: Path, work: Callable[[SessionFactory], Awaitable[T]]) -> T:
    """Create the tables and outlets 1 and 2 in a throwaway database, then run `work`."""

    async def main() -> T:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/seed.db")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                session.add(Outlet(id=1, slug="fridge", name="Fridge", ip="1.1.1.1"))
                session.add(Outlet(id=2, slug="desk", name="Desk", ip="1.1.1.2"))
                await session.commit()
            return await work(factory)
        finally:
            await engine.dispose()

    return asyncio.run(main())


async def rows(factory: SessionFactory) -> Rows:
    """Every stored hour as {(outlet_id, hour_start): (kwh, seconds_covered)}."""
    async with factory() as session:
        found = (await session.execute(select(HourlyEnergy))).scalars().all()
    return {(row.outlet_id, row.hour_start): (row.kwh, row.seconds_covered) for row in found}


async def seeded(factory: SessionFactory, days: int, now: datetime = NOW) -> Rows:
    await seed_demo(factory, OUTLETS, days, TZ, BILLING, now)
    return await rows(factory)


def local_hour(day: tuple[int, int, int], hour: int) -> datetime:
    """A whole local (Montevideo) hour, as the aware UTC time the table stores."""
    return datetime(*day, hour, tzinfo=TZ).astimezone(UTC)


def test_it_writes_every_hour_of_every_outlet_and_says_how_many(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> tuple[int, Rows]:
        written = await seed_demo(factory, OUTLETS, 3, TZ, BILLING, NOW)
        return written, await rows(factory)

    written, stored = run_with_factory(tmp_path, work)

    assert written == 3 * 24 * 2
    assert len(stored) == written
    assert {outlet_id for outlet_id, _ in stored} == {1, 2}
    assert all(seconds == 3600 for _, seconds in stored.values())


def test_the_history_ends_at_the_last_completed_hour(tmp_path: Path) -> None:
    stored = run_with_factory(tmp_path, lambda factory: seeded(factory, 3))

    hours = sorted({hour for _, hour in stored})
    current_hour = datetime(2026, 11, 10, 12, tzinfo=UTC)  # NOW is 12:30, so 12:00 is still going on
    assert hours[0] == current_hour - timedelta(hours=72)
    assert hours[-1] == current_hour - timedelta(hours=1)
    assert all(hour.utcoffset() == timedelta(0) for hour in hours)


def test_the_same_call_gives_the_same_data(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = run_with_factory(tmp_path / "a", lambda factory: seeded(factory, 3))
    second = run_with_factory(tmp_path / "b", lambda factory: seeded(factory, 3))

    assert first == second


def test_a_table_with_data_is_left_alone(tmp_path: Path) -> None:
    real_hour = datetime(2026, 11, 1, 8, tzinfo=UTC)

    async def work(factory: SessionFactory) -> tuple[int, Rows]:
        async with factory() as session:
            session.add(HourlyEnergy(outlet_id=1, hour_start=real_hour, kwh=0.5, seconds_covered=3600))
            await session.commit()
        written = await seed_demo(factory, OUTLETS, 3, TZ, BILLING, NOW)
        return written, await rows(factory)

    written, stored = run_with_factory(tmp_path, work)

    assert written == 0
    assert stored == {(1, real_hour): (0.5, 3600)}


def test_zero_days_writes_nothing(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> tuple[int, Rows]:
        written = await seed_demo(factory, OUTLETS, 0, TZ, BILLING, NOW)
        return written, await rows(factory)

    assert run_with_factory(tmp_path, work) == (0, {})


def test_every_value_is_in_the_range_of_its_appliance(tmp_path: Path) -> None:
    stored = run_with_factory(tmp_path, lambda factory: seeded(factory, 30))

    fridge = [kwh for (outlet_id, _), (kwh, _) in stored.items() if outlet_id == 1]
    desk = [kwh for (outlet_id, _), (kwh, _) in stored.items() if outlet_id == 2]
    assert all(0.038 <= kwh <= 0.128 for kwh in fridge)
    assert all(0.004 <= kwh <= 0.008 or 0.11 <= kwh <= 0.21 for kwh in desk)


def test_the_desk_follows_the_local_working_day(tmp_path: Path) -> None:
    thursday = (2026, 4, 30)
    friday_holiday = (2026, 5, 1)  # Día de los Trabajadores, a weekday that is a holiday
    now = datetime(2026, 5, 5, tzinfo=UTC)

    stored = run_with_factory(tmp_path, lambda factory: seeded(factory, 5, now))

    def desk(day: tuple[int, int, int], hour: int) -> float:
        return stored[(2, local_hour(day, hour))][0]

    assert desk(thursday, 10) >= 0.11  # a working day, 10:00 local
    assert desk(thursday, 3) <= 0.008  # the middle of the night
    assert desk(friday_holiday, 10) <= 0.008  # a holiday is treated like a day off: idle in the morning

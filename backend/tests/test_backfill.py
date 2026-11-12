import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.backfill
from app.backfill import MIN_TRUSTED_SECONDS, backfill_loop, backfill_once, store_device_hours
from app.clients import OutletClient
from app.db import Base, HourlyEnergy, Outlet
from app.outlets import OutletInfo

NOW = datetime(2026, 11, 10, 12, 30, tzinfo=UTC)
TZ = ZoneInfo("America/Montevideo")
SessionFactory = async_sessionmaker[AsyncSession]


def hour(hours_ago: int) -> datetime:
    """The start of a whole UTC hour, `hours_ago` hours before the hour that contains NOW."""
    return NOW.replace(minute=0) - timedelta(hours=hours_ago)


def run_with_factory[T](tmp_path: Path, work: Callable[[SessionFactory], Awaitable[T]]) -> T:
    """Create the tables and outlets 1 and 2 in a throwaway database, then run `work`."""

    async def main() -> T:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/backfill.db")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                session.add(Outlet(id=1, slug="a", name="A", ip="1.1.1.1"))
                session.add(Outlet(id=2, slug="b", name="B", ip="1.1.1.2"))
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


# --- backfill_once and backfill_loop ---------------------------------------------------------------


class FakeHistoryClient:
    """Answers the history request with a list, an exception, or never."""

    def __init__(self, result: list[tuple[datetime, float]] | Exception | None = None) -> None:
        self._result = result  # None: hang
        self.requests: list[tuple[date, date]] = []

    async def read_power_w(self) -> float:
        return 0.0

    async def read_hourly_wh(self, first_day: date, last_day: date) -> list[tuple[datetime, float]]:
        self.requests.append((first_day, last_day))
        if self._result is None:
            await asyncio.sleep(3600)
        if isinstance(self._result, Exception):
            raise self._result
        assert self._result is not None
        return self._result


def info(outlet_id: int) -> OutletInfo:
    return OutletInfo(id=outlet_id, slug="ab"[outlet_id - 1], name="X", ip="1.1.1.1", model="p110")


OUTLETS = [info(1), info(2)]


def as_clients(*clients: FakeHistoryClient) -> dict[int, OutletClient]:
    return {i + 1: client for i, client in enumerate(clients)}


def test_each_plug_history_goes_to_its_own_outlet(tmp_path: Path) -> None:
    clients = as_clients(FakeHistoryClient([(hour(3), 100.0)]), FakeHistoryClient([(hour(2), 40.0)]))

    async def work(factory: SessionFactory) -> tuple[int, list[tuple[int, datetime]]]:
        total = await backfill_once(factory, clients, OUTLETS, TZ, NOW)
        async with factory() as session:
            found = (await session.execute(select(HourlyEnergy))).scalars().all()
        return total, sorted((row.outlet_id, row.hour_start) for row in found)

    total, stored = run_with_factory(tmp_path, work)

    assert total == 2
    assert stored == [(1, hour(3)), (2, hour(2))]


def test_it_asks_for_eight_days_ending_today_in_the_local_time_zone(tmp_path: Path) -> None:
    client = FakeHistoryClient([])
    late = datetime(2026, 11, 10, 1, 0, tzinfo=UTC)  # still 9 November (22:00) in Montevideo

    async def work(factory: SessionFactory) -> int:
        return await backfill_once(factory, as_clients(client), OUTLETS[:1], TZ, late)

    run_with_factory(tmp_path, work)

    assert client.requests == [(date(2026, 11, 2), date(2026, 11, 9))]


def test_a_failing_plug_is_logged_and_the_others_still_run(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clients = as_clients(FakeHistoryClient(ConnectionError("offline")), FakeHistoryClient([(hour(2), 40.0)]))

    async def work(factory: SessionFactory) -> int:
        return await backfill_once(factory, clients, OUTLETS, TZ, NOW)

    caplog.set_level("WARNING", logger="tapo.backfill")
    total = run_with_factory(tmp_path, work)

    assert total == 1
    assert "outlet 'a'" in caplog.text
    assert "offline" in caplog.text


def test_a_plug_that_does_not_answer_times_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.backfill, "BACKFILL_TIMEOUT_SECONDS", 0.02)
    clients = as_clients(FakeHistoryClient(None), FakeHistoryClient([(hour(2), 40.0)]))

    async def work(factory: SessionFactory) -> int:
        return await backfill_once(factory, clients, OUTLETS, TZ, NOW)

    assert run_with_factory(tmp_path, work) == 1


def test_the_loop_imports_at_start_and_again_after_the_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.backfill, "BACKFILL_INTERVAL_SECONDS", 0.02)
    client = FakeHistoryClient([(hour(2), 40.0)])

    async def work(factory: SessionFactory) -> int:
        task = asyncio.create_task(backfill_loop(factory, as_clients(client), OUTLETS[:1], TZ, clock=lambda: NOW))
        await asyncio.sleep(0.07)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return len(client.requests)

    assert run_with_factory(tmp_path, work) >= 2

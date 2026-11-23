import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.poller
from app.clients import OutletClient
from app.db import Base, HourlyEnergy, Outlet, Reading
from app.energy import record_sample
from app.live import LiveHub
from app.outlets import OutletInfo
from app.poller import Poller
from app.settings import Settings

T0 = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
SessionFactory = async_sessionmaker[AsyncSession]


class FakeClient:
    """Plays a script: each read returns the next power, or raises the next exception.

    The last item repeats forever.
    """

    def __init__(self, *script: float | Exception) -> None:
        self._script = list(script)
        self.calls = 0

    async def read_power_w(self) -> float:
        self.calls += 1
        item = self._script.pop(0) if len(self._script) > 1 else self._script[0]
        if isinstance(item, Exception):
            raise item
        return item

    async def read_hourly_wh(self, first_day: date, last_day: date) -> list[tuple[datetime, float]]:
        return []  # the poller never asks for history


class HangingClient:
    async def read_power_w(self) -> float:
        await asyncio.sleep(3600)
        return 0.0

    async def read_hourly_wh(self, first_day: date, last_day: date) -> list[tuple[datetime, float]]:
        return []


def run_with_factory[T](tmp_path: Path, work: Callable[[SessionFactory], Awaitable[T]]) -> T:
    """Create the tables and outlets 1 and 2 in a throwaway database, then run `work`."""

    async def main() -> T:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/poller.db")
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


class Setup:
    """A poller with fake plugs and a clock the test moves by hand."""

    def __init__(
        self, factory: SessionFactory, clients: dict[int, OutletClient], settings: Settings | None = None
    ) -> None:
        self.now = T0
        self.hub = LiveHub()
        outlets = [OutletInfo(id=i, slug="ab"[i - 1], name="x", ip="x", model="p110") for i in clients]
        self.poller = Poller(
            settings or Settings(_env_file=None),
            factory,
            self.hub,
            clients,
            outlets,
            clock=lambda: self.now,
        )

    async def round_at(self, seconds: int) -> None:
        self.now = T0 + timedelta(seconds=seconds)
        await self.poller.poll_once()


async def reading_count(factory: SessionFactory, outlet_id: int) -> int:
    async with factory() as session:
        stmt = select(func.count()).select_from(Reading).where(Reading.outlet_id == outlet_id)
        return (await session.execute(stmt)).scalar_one()


async def hourly_rows(factory: SessionFactory) -> list[HourlyEnergy]:
    async with factory() as session:
        return list((await session.execute(select(HourlyEnergy))).scalars())


def test_a_good_round_stores_the_reading_and_publishes_it(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> None:
        s = Setup(factory, {1: FakeClient(42.5)})
        await s.round_at(0)

        # Counted from a new session: the reading was committed, not just added.
        assert await reading_count(factory, 1) == 1
        [live] = s.hub.snapshot()
        assert (live.outlet_id, live.power_w, live.online, live.ts) == (1, 42.5, True, T0)

    run_with_factory(tmp_path, work)


def test_two_rounds_store_the_energy_between_them(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> None:
        s = Setup(factory, {1: FakeClient(100.0, 200.0)})
        await s.round_at(0)
        await s.round_at(10)

        [row] = await hourly_rows(factory)
        assert row.kwh == pytest.approx(150.0 * 10 / 3_600_000)  # average power times 10 s
        assert row.seconds_covered == 10

    run_with_factory(tmp_path, work)


def test_a_failing_plug_is_published_offline_and_stores_nothing(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> None:
        s = Setup(factory, {1: FakeClient(ConnectionError("down"))})
        await s.round_at(0)

        assert await reading_count(factory, 1) == 0
        [live] = s.hub.snapshot()
        assert (live.power_w, live.online) == (None, False)

    run_with_factory(tmp_path, work)


def test_an_outage_is_not_bridged(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> None:
        client = FakeClient(100.0, ConnectionError("down"), 100.0)
        s = Setup(factory, {1: client})
        await s.round_at(0)
        await s.round_at(10)  # fails
        await s.round_at(20)  # back; 20 s since the last good sample is within the gap limit

        assert await reading_count(factory, 1) == 2
        assert await hourly_rows(factory) == []  # but no energy was invented for the outage

    run_with_factory(tmp_path, work)


def test_one_failing_plug_does_not_affect_another(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> None:
        s = Setup(factory, {1: FakeClient(ConnectionError("down")), 2: FakeClient(30.0)})
        await s.round_at(0)

        assert await reading_count(factory, 1) == 0
        assert await reading_count(factory, 2) == 1
        assert [(r.outlet_id, r.online) for r in s.hub.snapshot()] == [(1, False), (2, True)]

    run_with_factory(tmp_path, work)


def test_failures_are_logged_sparingly_and_recovery_once(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    async def work(factory: SessionFactory) -> None:
        s = Setup(factory, {1: FakeClient(*[ConnectionError("down")] * 21, 5.0)})
        for i in range(22):
            await s.round_at(i * 10)

    caplog.set_level(logging.INFO, logger="tapo.poller")
    run_with_factory(tmp_path, work)

    messages = [r.getMessage() for r in caplog.records]
    unreachable = [m for m in messages if "unreachable" in m]
    assert len(unreachable) == 2  # the 1st failure and the 20th
    assert "(1 in a row)" in unreachable[0]
    assert "(20 in a row)" in unreachable[1]
    assert sum("back online" in m for m in messages) == 1


def test_a_hanging_plug_times_out_and_does_not_hold_up_the_others(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> None:
        s = Setup(
            factory, {1: HangingClient(), 2: FakeClient(30.0)}, Settings(poll_interval_seconds=1, _env_file=None)
        )
        await asyncio.wait_for(s.round_at(0), timeout=5)

        assert [(r.outlet_id, r.online) for r in s.hub.snapshot()] == [(1, False), (2, True)]

    run_with_factory(tmp_path, work)


def test_a_storage_error_does_not_stop_the_other_plugs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    real_record_sample = record_sample

    async def flaky(session: AsyncSession, outlet_id: int, *args: object) -> None:
        if outlet_id == 1:
            raise RuntimeError("disk full")
        await real_record_sample(session, outlet_id, *args)  # type: ignore[arg-type]

    monkeypatch.setattr(app.poller, "record_sample", flaky)

    async def work(factory: SessionFactory) -> None:
        s = Setup(factory, {1: FakeClient(10.0), 2: FakeClient(20.0)})
        await s.round_at(0)  # must not raise

        assert await reading_count(factory, 1) == 0
        assert await reading_count(factory, 2) == 1
        assert [(r.outlet_id, r.online) for r in s.hub.snapshot()] == [(1, True), (2, True)]

    run_with_factory(tmp_path, work)

    assert "Could not store the reading of outlet 'a'" in caplog.text


def test_run_polls_repeatedly_until_cancelled(tmp_path: Path) -> None:
    async def work(factory: SessionFactory) -> int:
        client = FakeClient(10.0)
        s = Setup(factory, {1: client})
        task = asyncio.create_task(s.poller.run(interval=0.01))
        try:
            # Wait for the third poll, not for a fixed time: a slow machine then takes longer and still passes.
            # The limit only keeps a broken poller from hanging the test.
            async with asyncio.timeout(5):
                while client.calls < 3:
                    await asyncio.sleep(0.01)
        finally:
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task  # `run` only ends when it is cancelled
        return client.calls

    assert run_with_factory(tmp_path, work) >= 3

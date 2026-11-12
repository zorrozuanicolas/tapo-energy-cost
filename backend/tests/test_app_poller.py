import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

import app.main
import app.prune
from app.db import HourlyEnergy, Reading
from app.main import AppState, create_app
from app.outlets import load_outlets
from app.settings import Settings

from .conftest import CONFIG_DIR


def run_lifespan[T](tmp_path: Path, poller_enabled: bool, work: Callable[[AppState], Awaitable[T]]) -> T:
    """Start the app (mock plugs) on a database in `tmp_path`, run `work` on its state, shut it down."""
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'app.db').as_posix()}",
        config_dir=CONFIG_DIR,
        poller_enabled=poller_enabled,
    )

    async def main() -> T:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            result = await work(app.state.ctx)
        # After shutdown, no background task may be left running.
        assert asyncio.all_tasks() == {asyncio.current_task()}
        return result

    return asyncio.run(main())


async def count_readings(state: AppState) -> int:
    async with state.session_factory() as session:
        return (await session.execute(select(func.count()).select_from(Reading))).scalar_one()


def test_the_poller_runs_with_the_app_and_stops_with_it(tmp_path: Path) -> None:
    async def work(state: AppState) -> tuple[int, int]:
        await asyncio.sleep(0.3)  # the first round starts at once
        return await count_readings(state), len(state.hub.snapshot())

    readings, live = run_lifespan(tmp_path, True, work)

    outlets = len(load_outlets(CONFIG_DIR))
    assert readings == outlets  # one reading per plug, from the first round
    assert live == outlets


def test_nothing_is_polled_when_the_poller_is_off(tmp_path: Path) -> None:
    async def work(state: AppState) -> tuple[int, int]:
        await asyncio.sleep(0.3)
        return await count_readings(state), len(state.hub.snapshot())

    assert run_lifespan(tmp_path, False, work) == (0, 0)


def test_old_readings_are_pruned_even_when_the_poller_is_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.prune, "PRUNE_INTERVAL_SECONDS", 0.02)

    async def work(state: AppState) -> int:
        async with state.session_factory() as session:
            old = datetime.now(UTC) - timedelta(days=state.settings.raw_retention_days + 10)
            session.add(Reading(outlet_id=state.outlets[0].id, ts=old, power_w=5.0))
            await session.commit()
        await asyncio.sleep(0.2)
        return await count_readings(state)

    assert run_lifespan(tmp_path, False, work) == 0


class HistoryPlug:
    """A plug with two finished hours of history and a steady power."""

    async def read_power_w(self) -> float:
        return 1.0

    async def read_hourly_wh(self, first_day: date, last_day: date) -> list[tuple[datetime, float]]:
        hour = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        return [(hour - timedelta(hours=3), 100.0), (hour - timedelta(hours=2), 50.0)]


async def count_hours(state: AppState) -> int:
    async with state.session_factory() as session:
        return (await session.execute(select(func.count()).select_from(HourlyEnergy))).scalar_one()


def test_the_history_of_the_plugs_is_imported_at_startup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.main, "make_client", lambda outlet, index, settings, tz: HistoryPlug())

    async def work(state: AppState) -> int:
        await asyncio.sleep(0.3)
        return await count_hours(state)

    assert run_lifespan(tmp_path, True, work) == 2 * len(load_outlets(CONFIG_DIR))


def test_the_plugs_are_not_asked_for_history_when_the_poller_is_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app.main, "make_client", lambda outlet, index, settings, tz: HistoryPlug())

    async def work(state: AppState) -> int:
        await asyncio.sleep(0.3)
        return await count_hours(state)

    assert run_lifespan(tmp_path, False, work) == 0

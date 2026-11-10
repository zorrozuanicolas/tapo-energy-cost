import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from sqlalchemy import func, select

from app.db import Reading
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

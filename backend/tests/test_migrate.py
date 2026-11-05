import asyncio
import logging
import sqlite3
from pathlib import Path

from app.migrate import upgrade_database, upgrade_database_async


def _url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.as_posix()}"


def _tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {name for (name,) in rows}


# The sync tests are plain functions on purpose: migrations/env.py calls asyncio.run itself.


def test_upgrade_creates_the_tables(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    upgrade_database(_url(db))
    assert {"outlets", "readings", "hourly_energy"} <= _tables(db)


def test_upgrading_twice_is_harmless(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    upgrade_database(_url(db))
    upgrade_database(_url(db))
    assert {"outlets", "readings", "hourly_energy"} <= _tables(db)


def test_async_upgrade_works_inside_a_running_event_loop(tmp_path: Path) -> None:
    db = tmp_path / "app.db"

    async def main() -> None:
        await upgrade_database_async(_url(db))

    asyncio.run(main())
    assert {"outlets", "readings", "hourly_energy"} <= _tables(db)


def test_upgrade_does_not_silence_existing_loggers(tmp_path: Path) -> None:
    logger = logging.getLogger("tapo.test_migrate")
    upgrade_database(_url(tmp_path / "app.db"))
    assert not logger.disabled

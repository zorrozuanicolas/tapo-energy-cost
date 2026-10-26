import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db import Base, Outlet, Reading, make_engine, make_session_factory, utcnow


def run_with_engine[T](db_path: Path, work: Callable[[AsyncEngine], Awaitable[T]]) -> T:
    """Run `work` against an engine on `db_path`, with the tables created."""

    async def main() -> T:
        engine = make_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            return await work(engine)
        finally:
            await engine.dispose()

    return asyncio.run(main())


def test_engine_creates_the_database_folder(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "data" / "tapo.db"

    make_engine(f"sqlite+aiosqlite:///{db_path}")

    assert db_path.parent.is_dir()


def test_sqlite_uses_wal_journal(tmp_path: Path) -> None:
    async def work(engine: AsyncEngine) -> object:
        async with engine.connect() as conn:
            return (await conn.execute(text("PRAGMA journal_mode"))).scalar_one()

    assert run_with_engine(tmp_path / "wal.db", work) == "wal"


def test_sqlite_enforces_foreign_keys(tmp_path: Path) -> None:
    async def work(engine: AsyncEngine) -> object:
        async with engine.connect() as conn:
            return (await conn.execute(text("PRAGMA foreign_keys"))).scalar_one()

    assert run_with_engine(tmp_path / "fk.db", work) == 1


def test_reading_of_unknown_outlet_is_rejected(tmp_path: Path) -> None:
    async def work(engine: AsyncEngine) -> None:
        async with make_session_factory(engine)() as session:
            session.add(Reading(outlet_id=99, ts=utcnow(), power_w=1.0))
            await session.commit()

    with pytest.raises(IntegrityError):
        run_with_engine(tmp_path / "orphan.db", work)


def test_objects_stay_readable_after_commit(tmp_path: Path) -> None:
    async def work(engine: AsyncEngine) -> str:
        async with make_session_factory(engine)() as session:
            outlet = Outlet(slug="a", name="A", ip="1.1.1.1")
            session.add(outlet)
            await session.commit()
            return outlet.slug

    assert run_with_engine(tmp_path / "expire.db", work) == "a"

"""Apply the Alembic migrations from code, so the app can bring its own database up to date."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def upgrade_database(url: str) -> None:
    """Bring the database at `url` to the latest migration (`alembic upgrade head`)."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")


async def upgrade_database_async(url: str) -> None:
    """Same, for async code. migrations/env.py calls asyncio.run, which cannot run inside a
    running event loop, so the upgrade runs in a worker thread that has none."""
    await asyncio.to_thread(upgrade_database, url)

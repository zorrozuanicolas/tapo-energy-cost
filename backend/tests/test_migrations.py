import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.db import Base

ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"

# These tests are sync on purpose: migrations/env.py calls asyncio.run itself.


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "migrated.db"


@pytest.fixture
def alembic_config(db_path: Path) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    return config


def _tables_and_indexes(db_path: Path) -> tuple[set[str], set[str]]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute("SELECT type, name FROM sqlite_master").fetchall()
    tables = {name for kind, name in rows if kind == "table"}
    indexes = {name for kind, name in rows if kind == "index"}
    return tables, indexes


def test_upgrade_creates_tables_and_index(alembic_config: Config, db_path: Path) -> None:
    command.upgrade(alembic_config, "head")

    tables, indexes = _tables_and_indexes(db_path)
    assert {"outlets", "readings", "hourly_energy"} <= tables
    assert "ix_readings_outlet_ts" in indexes


def test_downgrade_removes_everything(alembic_config: Config, db_path: Path) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")

    tables, indexes = _tables_and_indexes(db_path)
    # Alembic keeps its own bookkeeping table.
    assert tables - {"alembic_version"} == set()
    assert "ix_readings_outlet_ts" not in indexes


def test_migrated_schema_matches_models(alembic_config: Config, db_path: Path) -> None:
    """Fails when a model changes without a new migration."""
    command.upgrade(alembic_config, "head")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()

    assert diff == []

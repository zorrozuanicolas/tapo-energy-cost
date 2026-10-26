import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select

from app.billing import ConfigError
from app.db import Base, Outlet, make_engine, make_session_factory
from app.outlets import OutletConfig, OutletInfo, load_outlets, sync_outlets
from tests.conftest import CONFIG_DIR


def write_outlets(tmp_path: Path, text: str) -> Path:
    (tmp_path / "outlets.yaml").write_text(text, encoding="utf-8")
    return tmp_path


def test_real_outlets_file_loads() -> None:
    outlets = load_outlets(CONFIG_DIR)

    assert outlets
    assert all(outlet.model in ("p110", "p115") for outlet in outlets)


def test_model_defaults_to_p110(tmp_path: Path) -> None:
    config_dir = write_outlets(tmp_path, "outlets:\n  - {slug: a, name: A, ip: 1.1.1.1}\n")

    assert load_outlets(config_dir)[0].model == "p110"


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Missing configuration file"):
        load_outlets(tmp_path)


@pytest.mark.parametrize("text", ["", "outlets: []\n", "plugs:\n  - {slug: a}\n"])
def test_empty_or_absent_list_is_rejected(tmp_path: Path, text: str) -> None:
    with pytest.raises(ConfigError, match="non-empty 'outlets' list"):
        load_outlets(write_outlets(tmp_path, text))


def test_missing_field_is_rejected(tmp_path: Path) -> None:
    config_dir = write_outlets(tmp_path, "outlets:\n  - {slug: a, name: A}\n")

    with pytest.raises(ConfigError, match=r"outlets\[0\]"):
        load_outlets(config_dir)


def test_duplicated_slug_is_rejected(tmp_path: Path) -> None:
    config_dir = write_outlets(
        tmp_path,
        "outlets:\n  - {slug: a, name: A, ip: 1.1.1.1}\n  - {slug: a, name: B, ip: 2.2.2.2}\n",
    )

    with pytest.raises(ConfigError, match="duplicated slug 'a'"):
        load_outlets(config_dir)


def test_unknown_model_is_rejected(tmp_path: Path) -> None:
    config_dir = write_outlets(tmp_path, "outlets:\n  - {slug: a, name: A, ip: 1.1.1.1, model: p300}\n")

    with pytest.raises(ConfigError, match="model"):
        load_outlets(config_dir)


def sync_twice(
    tmp_path: Path, first: list[OutletConfig], second: list[OutletConfig]
) -> tuple[list[OutletInfo], list[OutletInfo], list[Outlet]]:
    """Sync `first`, then `second`; return both results and the final database rows."""

    async def main() -> tuple[list[OutletInfo], list[OutletInfo], list[Outlet]]:
        engine = make_engine(f"sqlite+aiosqlite:///{tmp_path}/outlets.db")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            factory = make_session_factory(engine)
            first_result = await sync_outlets(factory, first)
            second_result = await sync_outlets(factory, second)
            async with factory() as session:
                rows = list((await session.execute(select(Outlet).order_by(Outlet.id))).scalars())
            return first_result, second_result, rows
        finally:
            await engine.dispose()

    return asyncio.run(main())


A = OutletConfig(slug="a", name="A", ip="1.1.1.1")
B = OutletConfig(slug="b", name="B", ip="2.2.2.2", model="p115")


def test_sync_creates_outlets_in_config_order(tmp_path: Path) -> None:
    first, _, rows = sync_twice(tmp_path, [A, B], [A, B])

    assert [info.slug for info in first] == ["a", "b"]
    assert [info.model for info in first] == ["p110", "p115"]
    assert [row.slug for row in rows] == ["a", "b"]


def test_sync_updates_existing_outlet_and_keeps_its_id(tmp_path: Path) -> None:
    renamed = OutletConfig(slug="a", name="Renamed", ip="9.9.9.9")

    first, second, rows = sync_twice(tmp_path, [A], [renamed])

    assert second[0].id == first[0].id
    assert (rows[0].name, rows[0].ip) == ("Renamed", "9.9.9.9")
    assert len(rows) == 1


def test_sync_keeps_outlets_removed_from_the_config(tmp_path: Path) -> None:
    _, _, rows = sync_twice(tmp_path, [A, B], [A])

    assert [row.slug for row in rows] == ["a", "b"]

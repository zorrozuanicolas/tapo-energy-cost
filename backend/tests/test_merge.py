import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.merge
from app.db import Base, HourlyEnergy, Outlet, Reading
from app.merge import MergeError, describe, main, merge_databases

NOON = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)

# (outlet id, hours after noon, kWh, seconds covered) and (outlet id, seconds after noon, watts)
HourRow = tuple[int, int, float, int]
ReadingRow = tuple[int, int, float]


def stored(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S.%f")


def make_source(
    path: Path,
    hours: list[HourRow] | None = None,
    readings: list[ReadingRow] | None = None,
    outlets: list[tuple[int, str, str, str]] | None = None,
) -> Path:
    """A database laid out like the old app's: a `position` column and no Alembic table."""
    with closing(sqlite3.connect(path)) as db:
        db.executescript(
            """
            CREATE TABLE outlets (id INTEGER PRIMARY KEY, slug TEXT, name TEXT, ip TEXT, position INTEGER);
            CREATE TABLE readings (id INTEGER PRIMARY KEY, outlet_id INTEGER, ts DATETIME, power_w FLOAT);
            CREATE TABLE hourly_energy (outlet_id INTEGER, hour_start DATETIME, kwh FLOAT, seconds_covered INTEGER,
                PRIMARY KEY (outlet_id, hour_start));
            """
        )
        db.executemany("INSERT INTO outlets VALUES (?, ?, ?, ?, 0)", outlets or [(1, "desk", "Desk", "10.0.0.1")])
        db.executemany(
            "INSERT INTO hourly_energy VALUES (?, ?, ?, ?)",
            [(o, stored(NOON + timedelta(hours=h)), kwh, seconds) for o, h, kwh, seconds in hours or []],
        )
        db.executemany(
            "INSERT INTO readings (outlet_id, ts, power_w) VALUES (?, ?, ?)",
            [(o, stored(NOON + timedelta(seconds=s)), watts) for o, s, watts in readings or []],
        )
        db.commit()
    return path


def merged_hours(path: Path) -> list[tuple[str, int, float, int]]:
    """(slug, hours after noon, kWh, seconds covered), read through the app's own models."""
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        with Session(engine) as session:
            rows = session.execute(select(Outlet.slug, HourlyEnergy).join(HourlyEnergy)).all()
            return sorted(
                (slug, (row.hour_start - NOON) // timedelta(hours=1), row.kwh, row.seconds_covered)
                for slug, row in rows
            )
    finally:
        engine.dispose()


def test_hours_from_all_sources_are_kept_and_the_better_covered_row_wins(tmp_path: Path) -> None:
    first = make_source(tmp_path / "first.db", hours=[(1, 0, 0.10, 3600), (1, 1, 0.20, 3600), (1, 2, 0.01, 300)])
    second = make_source(tmp_path / "second.db", hours=[(1, 1, 0.05, 900), (1, 2, 0.30, 3600), (1, 3, 0.40, 3600)])

    merged = merge_databases(tmp_path / "out.db", [first, second])

    assert merged_hours(tmp_path / "out.db") == [
        ("desk", 0, 0.10, 3600),
        ("desk", 1, 0.20, 3600),  # the first source covers more of it
        ("desk", 2, 0.30, 3600),  # the second one does
        ("desk", 3, 0.40, 3600),
    ]
    assert merged.hours_taken == [2, 2]


@pytest.mark.parametrize(("order", "kwh"), [((0, 1), 0.2), ((1, 0), 0.1)])
def test_on_a_tie_the_source_listed_later_wins(tmp_path: Path, order: tuple[int, int], kwh: float) -> None:
    sources = [
        make_source(tmp_path / "a.db", hours=[(1, 0, 0.1, 3600)]),
        make_source(tmp_path / "b.db", hours=[(1, 0, 0.2, 3600)]),
    ]

    merge_databases(tmp_path / "out.db", [sources[i] for i in order])

    assert merged_hours(tmp_path / "out.db") == [("desk", 0, kwh, 3600)]


def test_plugs_are_matched_by_slug_even_when_their_ids_differ(tmp_path: Path) -> None:
    first = make_source(
        tmp_path / "first.db",
        outlets=[(1, "desk", "Desk", "10.0.0.1"), (2, "fridge", "Fridge", "10.0.0.2")],
        hours=[(1, 0, 0.1, 3600), (2, 0, 0.2, 3600)],
    )
    second = make_source(
        tmp_path / "second.db",
        outlets=[(1, "fridge", "Kitchen fridge", "10.0.0.9"), (2, "desk", "Desk", "10.0.0.1")],
        hours=[(1, 1, 0.3, 3600), (2, 1, 0.4, 3600)],
    )

    merged = merge_databases(tmp_path / "out.db", [first, second])

    assert merged_hours(tmp_path / "out.db") == [
        ("desk", 0, 0.1, 3600),
        ("desk", 1, 0.4, 3600),
        ("fridge", 0, 0.2, 3600),
        ("fridge", 1, 0.3, 3600),
    ]
    # The last source describes the plug as it is now.
    assert merged.plugs["fridge"].name == "Kitchen fridge"
    assert merged.plugs["fridge"].ip == "10.0.0.9"


def test_readings_are_combined_without_duplicates(tmp_path: Path) -> None:
    first = make_source(tmp_path / "first.db", readings=[(1, 0, 10.0), (1, 10, 11.0)])
    second = make_source(tmp_path / "second.db", readings=[(1, 10, 11.0), (1, 20, 12.0)])

    merge_databases(tmp_path / "out.db", [first, second])

    engine = create_engine(f"sqlite:///{(tmp_path / 'out.db').as_posix()}")
    try:
        with Session(engine) as session:
            readings = session.execute(select(Reading.ts, Reading.power_w).order_by(Reading.ts)).all()
    finally:
        engine.dispose()
    assert [((ts - NOON).seconds, watts) for ts, watts in readings] == [(0, 10.0), (10, 11.0), (20, 12.0)]


def test_the_result_has_the_apps_schema_and_is_a_single_file(tmp_path: Path) -> None:
    source = make_source(tmp_path / "old.db", hours=[(1, 0, 0.1, 3600)])

    merge_databases(tmp_path / "result" / "out.db", [source])

    assert [p.name for p in (tmp_path / "result").iterdir()] == ["out.db"]
    engine = create_engine(f"sqlite:///{(tmp_path / 'result' / 'out.db').as_posix()}")
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            assert context.get_current_revision() is not None
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()


def test_the_sources_are_not_changed(tmp_path: Path) -> None:
    source = make_source(tmp_path / "source.db", hours=[(1, 0, 0.1, 3600)], readings=[(1, 0, 5.0)])
    before = source.read_bytes()

    merge_databases(tmp_path / "out.db", [source])

    assert source.read_bytes() == before


def test_rows_still_in_the_wal_of_a_source_in_use_are_included(tmp_path: Path) -> None:
    source = make_source(tmp_path / "source.db")

    with closing(sqlite3.connect(source)) as running_app:
        running_app.execute("PRAGMA journal_mode=WAL")
        running_app.execute("PRAGMA wal_autocheckpoint=0")
        running_app.execute("INSERT INTO hourly_energy VALUES (1, ?, 0.5, 3600)", (stored(NOON),))
        running_app.commit()
        assert (tmp_path / "source.db-wal").stat().st_size > 0

        merge_databases(tmp_path / "out.db", [source])

    assert merged_hours(tmp_path / "out.db") == [("desk", 0, 0.5, 3600)]


def test_a_source_left_with_a_wal_file_is_read_and_left_as_it_was(tmp_path: Path) -> None:
    running = make_source(tmp_path / "running.db")
    source = tmp_path / "crashed.db"
    wal = tmp_path / "crashed.db-wal"
    with closing(sqlite3.connect(running)) as app_db:
        app_db.execute("PRAGMA journal_mode=WAL")
        app_db.execute("PRAGMA wal_autocheckpoint=0")
        app_db.execute("INSERT INTO hourly_energy VALUES (1, ?, 0.5, 3600)", (stored(NOON),))
        app_db.commit()
        # The files as a power cut would leave them: the new row is only in the WAL.
        source.write_bytes(running.read_bytes())
        wal.write_bytes((tmp_path / "running.db-wal").read_bytes())
    before = source.read_bytes(), wal.read_bytes()

    merge_databases(tmp_path / "out.db", [source])

    assert merged_hours(tmp_path / "out.db") == [("desk", 0, 0.5, 3600)]
    # A connection allowed to write would move the WAL into the database when it closed.
    assert (source.read_bytes(), wal.read_bytes()) == before


@pytest.mark.parametrize("existing", ["out.db", "out.db-wal", "out.db-shm"])
def test_nothing_is_overwritten(tmp_path: Path, existing: str) -> None:
    source = make_source(tmp_path / "source.db")
    (tmp_path / existing).write_bytes(b"precious")

    with pytest.raises(MergeError, match="already exists"):
        merge_databases(tmp_path / "out.db", [source])

    assert (tmp_path / existing).read_bytes() == b"precious"


@pytest.mark.parametrize("content", [None, b"this is not a database" * 100])
def test_an_unreadable_source_fails_without_creating_the_output(tmp_path: Path, content: bytes | None) -> None:
    good = make_source(tmp_path / "good.db")
    bad = tmp_path / "bad.db"
    if content is not None:
        bad.write_bytes(content)

    with pytest.raises(MergeError):
        merge_databases(tmp_path / "out.db", [good, bad])

    assert not (tmp_path / "out.db").exists()
    assert bad.exists() == (content is not None)  # a missing source is not created


def test_data_for_an_unknown_outlet_is_an_error(tmp_path: Path) -> None:
    source = make_source(tmp_path / "source.db", hours=[(7, 0, 0.1, 3600)])

    with pytest.raises(MergeError, match="outlet 7"):
        merge_databases(tmp_path / "out.db", [source])


def test_a_result_that_fails_the_check_is_not_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = make_source(tmp_path / "source.db", hours=[(1, 0, 0.1, 3600), (1, 1, 0.2, 3600)])
    write = app.merge.write_database

    def write_and_lose_a_row(path: Path, merged: app.merge.Merged) -> None:
        write(path, merged)
        with closing(sqlite3.connect(path)) as db:
            db.execute("DELETE FROM hourly_energy WHERE kwh = 0.2")
            db.commit()

    monkeypatch.setattr(app.merge, "write_database", write_and_lose_a_row)

    with pytest.raises(MergeError, match="does not hold"):
        merge_databases(tmp_path / "out.db", [source])

    assert [p.name for p in tmp_path.iterdir()] == ["source.db"]


def test_the_report_shows_the_stretches_of_data_in_local_time(tmp_path: Path) -> None:
    source = make_source(tmp_path / "source.db", hours=[(1, 0, 0.1, 3600), (1, 1, 0.2, 600), (1, 5, 0.3, 3600)])

    merged = merge_databases(tmp_path / "out.db", [source])
    report = describe(merged, [source], ZoneInfo("America/Montevideo"))

    assert report == [
        f"Hours taken from {source}: 3",
        "Total: 3 hourly rows and 0 readings",
        "",
        "desk: 3 hours, 0.600 kWh, 1 partly measured",
        "  2026-11-20 09:00 to 2026-11-20 11:00",  # noon UTC is 09:00 in Montevideo
        "  2026-11-20 14:00 to 2026-11-20 15:00",
    ]


def test_the_command_merges_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)  # away from any .env file
    source = make_source(tmp_path / "source.db", hours=[(1, 0, 0.1, 3600)])

    assert main(["out.db", str(source)]) == 0

    assert "Total: 1 hourly rows" in capsys.readouterr().out
    assert merged_hours(tmp_path / "out.db") == [("desk", 0, 0.1, 3600)]


def test_a_failed_command_exits_with_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["out.db", "missing.db"]) == 1

    assert "Merge failed" in capsys.readouterr().err

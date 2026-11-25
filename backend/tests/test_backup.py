import gzip
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.backup import NAME_FORMAT, BackupError, backup_database, database_path, main, prune_backups

NOW = datetime(2026, 11, 25, 6, 15, tzinfo=UTC)


def make_database(path: Path, values: list[int]) -> None:
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE sample (a INTEGER, b INTEGER)")
        db.executemany("INSERT INTO sample VALUES (?, ?)", [(v, -v) for v in values])
        db.commit()


def restored_values(backup: Path, tmp_path: Path) -> list[int]:
    """Restore a backup as the README does (unzip it) and read it."""
    restored = tmp_path / "restored.db"
    restored.write_bytes(gzip.decompress(backup.read_bytes()))
    with closing(sqlite3.connect(restored)) as db:
        return [row[0] for row in db.execute("SELECT a FROM sample ORDER BY a")]


def old_backup(folder: Path, age: timedelta) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (NOW - age).strftime(NAME_FORMAT)
    path.write_bytes(b"old")
    return path


def test_the_backup_restores_to_the_same_data(tmp_path: Path) -> None:
    make_database(tmp_path / "tapo.db", [1, 2, 3])

    backup = backup_database(tmp_path / "tapo.db", tmp_path / "backups", NOW)

    assert backup.name == "tapo-20261125-061500Z.db.gz"
    assert restored_values(backup, tmp_path) == [1, 2, 3]
    assert list((tmp_path / "backups").iterdir()) == [backup]  # no temporary files left


def test_rows_still_in_the_wal_are_included_while_the_database_is_in_use(tmp_path: Path) -> None:
    database = tmp_path / "tapo.db"
    make_database(database, [1])

    # Like the running app: a connection stays open and its latest rows are only in the WAL file.
    with closing(sqlite3.connect(database)) as app:
        app.execute("PRAGMA wal_autocheckpoint=0")
        app.execute("INSERT INTO sample VALUES (2, -2)")
        app.commit()
        assert (tmp_path / "tapo.db-wal").stat().st_size > 0

        backup = backup_database(database, tmp_path / "backups", NOW)

    assert restored_values(backup, tmp_path) == [1, 2]


def test_a_missing_database_is_an_error_and_is_not_created(tmp_path: Path) -> None:
    with pytest.raises(BackupError, match="no database"):
        backup_database(tmp_path / "tapo.db", tmp_path / "backups", NOW)

    assert list(tmp_path.iterdir()) == []


def test_a_database_that_fails_the_integrity_check_is_not_kept(tmp_path: Path) -> None:
    database = tmp_path / "tapo.db"
    make_database(database, [1, 2, 3])
    with closing(sqlite3.connect(database)) as db:
        db.execute("CREATE INDEX by_a ON sample (a)")
        # Redefine the index without rebuilding it, so its contents no longer match the table.
        db.execute("PRAGMA writable_schema=ON")
        db.execute("UPDATE sqlite_master SET sql = 'CREATE INDEX by_a ON sample (b)' WHERE name = 'by_a'")
        db.commit()

    with pytest.raises(BackupError, match="damaged"):
        backup_database(database, tmp_path / "backups", NOW)

    assert list((tmp_path / "backups").iterdir()) == []


def test_only_backups_older_than_the_limit_are_deleted(tmp_path: Path) -> None:
    expired = old_backup(tmp_path, timedelta(days=14, seconds=1))
    at_limit = old_backup(tmp_path, timedelta(days=14))
    recent = old_backup(tmp_path, timedelta(days=1))
    others = [tmp_path / "tapo-before-update.db.gz", tmp_path / "notes.txt"]
    for path in others:
        path.write_bytes(b"keep me")

    deleted = prune_backups(tmp_path, keep_days=14, now=NOW)

    assert deleted == [expired]
    assert sorted(tmp_path.iterdir()) == sorted([at_limit, recent, *others])


def test_the_command_backs_up_the_configured_database_and_prunes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)  # away from any .env file
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/data/tapo.db")
    (tmp_path / "data").mkdir()
    make_database(tmp_path / "data" / "tapo.db", [7])
    expired = old_backup(tmp_path / "data" / "backups", timedelta(days=3))

    assert main(["--keep-days", "2"]) == 0

    [backup] = (tmp_path / "data" / "backups").iterdir()
    assert backup != expired
    assert restored_values(backup, tmp_path) == [7]
    assert "Old backups deleted: 1" in capsys.readouterr().out


def test_a_failed_command_exits_with_1_and_keeps_the_old_backups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/tapo.db")
    (tmp_path / "tapo.db").write_bytes(b"this is not a database" * 100)
    expired = old_backup(tmp_path / "backups", timedelta(days=100))

    assert main([]) == 1

    assert list((tmp_path / "backups").iterdir()) == [expired]
    assert "Backup failed" in capsys.readouterr().err


def test_keep_days_below_1_is_rejected() -> None:
    with pytest.raises(SystemExit) as error:
        main(["--keep-days", "0"])

    assert error.value.code == 2


@pytest.mark.parametrize("url", ["sqlite+aiosqlite:///:memory:", "sqlite://", "postgresql://localhost/tapo"])
def test_only_a_sqlite_file_can_be_backed_up(url: str) -> None:
    with pytest.raises(BackupError):
        database_path(url)

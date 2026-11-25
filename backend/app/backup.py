"""Back up the SQLite database while the app keeps running: `python -m app.backup`.

Each run writes `backups/tapo-<UTC date and time>.db.gz` next to the database, then deletes the
backups older than `--keep-days`. It exits with 1, deleting nothing, if the new backup fails.
"""

import argparse
import gzip
import os
import shutil
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.engine import make_url

from .settings import Settings

DEFAULT_KEEP_DAYS = 14

# The date and time are part of the name, so a copied file keeps its age.
NAME_FORMAT = "tapo-%Y%m%d-%H%M%SZ.db.gz"


class BackupError(Exception):
    """The database could not be backed up."""


def database_path(url: str) -> Path:
    """The database file behind a SQLAlchemy SQLite URL."""
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or parsed.database in (None, "", ":memory:"):
        raise BackupError("only a SQLite database file can be backed up")
    return Path(parsed.database)


def _copy_and_check(database: Path, copy: Path) -> None:
    # Read-only: this must never change the database, or create an empty one.
    uri = f"{database.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as source, closing(sqlite3.connect(copy)) as target:
        # SQLite's online backup includes what is still in the WAL file, which copying the file would miss.
        source.backup(target)
        problems = [row[0] for row in target.execute("PRAGMA integrity_check")]
    if problems != ["ok"]:
        raise BackupError(f"the database is damaged: {problems[0]}")


def backup_database(database: Path, folder: Path, now: datetime) -> Path:
    """Write a checked, compressed copy of `database` into `folder` and return its path."""
    if not database.is_file():
        raise BackupError(f"there is no database at {database}")
    folder.mkdir(parents=True, exist_ok=True)
    final = folder / now.astimezone(UTC).strftime(NAME_FORMAT)

    # Work inside the destination folder, so the last step is a rename on the same disk.
    with TemporaryDirectory(prefix=".partial-", dir=folder) as work:
        copy = Path(work) / "copy.db"
        _copy_and_check(database, copy)
        compressed = Path(work) / "copy.db.gz"
        with copy.open("rb") as raw, compressed.open("wb") as out:
            with gzip.GzipFile(fileobj=out, mode="wb") as zipped:
                shutil.copyfileobj(raw, zipped)
            out.flush()
            os.fsync(out.fileno())  # on the disk before it gets its final name
        compressed.replace(final)
    return final


def prune_backups(folder: Path, keep_days: int, now: datetime) -> list[Path]:
    """Delete the backups older than `keep_days`, judged by their names. Other files are left alone."""
    limit = now - timedelta(days=keep_days)
    deleted: list[Path] = []
    for path in sorted(folder.glob("tapo-*.db.gz")):
        try:
            taken = datetime.strptime(path.name, NAME_FORMAT).replace(tzinfo=UTC)
        except ValueError:
            continue  # not a name this module writes, such as a renamed copy
        if taken < limit:
            path.unlink()
            deleted.append(path)
    return deleted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.backup", description="Back up the database.")
    parser.add_argument(
        "--keep-days", type=int, default=DEFAULT_KEEP_DAYS, help="delete older backups (default: %(default)s)"
    )
    args = parser.parse_args(argv)
    if args.keep_days < 1:
        parser.error("--keep-days must be at least 1")

    now = datetime.now(UTC)
    try:
        database = database_path(Settings().database_url)
        folder = database.parent / "backups"
        backup = backup_database(database, folder, now)
        deleted = prune_backups(folder, args.keep_days, now)
    except (BackupError, sqlite3.Error, OSError) as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        return 1
    print(f"Backup saved: {backup} ({backup.stat().st_size} bytes). Old backups deleted: {len(deleted)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Merge several databases into a new one: `python -m app.merge OUTPUT SOURCE [SOURCE ...]`.

For the history left by separate installations of the app (or of its predecessor) that read the same
plugs. The sources are opened read-only and the output must not exist yet.

- Plugs are matched by slug; the name and address come from the last source that has the plug.
- For an hour present in several sources, the row covering more of the hour wins. On a tie, the
  source listed later wins.
- Raw readings are combined; the same plug and instant is stored once.
"""

import argparse
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isclose
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, insert

from .backfill import MIN_TRUSTED_SECONDS
from .db import HourlyEnergy, Outlet, Reading
from .migrate import upgrade_database
from .settings import Settings

ONE_HOUR = timedelta(hours=1)

# A plug's slug and an instant in UTC: what identifies a row across databases, whose ids may differ.
Key = tuple[str, datetime]


class MergeError(Exception):
    """The databases could not be merged."""


@dataclass(frozen=True)
class Plug:
    name: str
    ip: str


@dataclass(frozen=True)
class Hour:
    kwh: float
    seconds_covered: int


@dataclass(frozen=True)
class Contents:
    """What one source database holds."""

    plugs: dict[str, Plug]
    hours: dict[Key, Hour]
    readings: dict[Key, float]


@dataclass(frozen=True)
class Merged:
    plugs: dict[str, Plug]
    hours: dict[Key, Hour]
    readings: dict[Key, float]
    # For each source, in the order given: how many of the merged hours were taken from it.
    hours_taken: list[int]


def _utc(text: str) -> datetime:
    # The app stores UTC without a zone (see `UtcDateTime`), and so did its predecessor.
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def read_source(path: Path) -> Contents:
    """Read a database without changing it."""
    if not path.is_file():
        raise MergeError(f"there is no database at {path}")
    uri = f"{path.resolve().as_uri()}?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True)) as db:
            # One transaction, so that an app writing meanwhile cannot make the tables disagree.
            db.execute("BEGIN")
            slugs: dict[int, str] = {}
            plugs: dict[str, Plug] = {}
            for outlet_id, slug, name, ip in db.execute("SELECT id, slug, name, ip FROM outlets ORDER BY id"):
                slugs[outlet_id] = slug
                plugs[slug] = Plug(name, ip)
            hours = {
                (slugs[outlet_id], _utc(start)): Hour(kwh, seconds)
                for outlet_id, start, kwh, seconds in db.execute(
                    "SELECT outlet_id, hour_start, kwh, seconds_covered FROM hourly_energy"
                )
            }
            readings = {
                (slugs[outlet_id], _utc(ts)): power_w
                for outlet_id, ts, power_w in db.execute("SELECT outlet_id, ts, power_w FROM readings")
            }
    except sqlite3.Error as exc:
        raise MergeError(f"cannot read {path}: {exc}") from exc
    except KeyError as exc:
        raise MergeError(f"{path} has data for outlet {exc}, which is not in its outlets table") from exc
    return Contents(plugs, hours, readings)


def combine(sources: list[Contents]) -> Merged:
    """Apply the merge rules, without touching any file."""
    plugs: dict[str, Plug] = {}
    hours: dict[Key, tuple[Hour, int]] = {}
    readings: dict[Key, float] = {}
    for index, source in enumerate(sources):
        plugs.update(source.plugs)
        readings.update(source.readings)
        for key, hour in source.hours.items():
            if key not in hours or hour.seconds_covered >= hours[key][0].seconds_covered:
                hours[key] = (hour, index)
    taken = [sum(1 for _, source_index in hours.values() if source_index == i) for i in range(len(sources))]
    return Merged(plugs, {key: hour for key, (hour, _) in hours.items()}, readings, taken)


def write_database(path: Path, merged: Merged) -> None:
    """Create a database with the app's current schema and fill it."""
    upgrade_database(f"sqlite+aiosqlite:///{path.as_posix()}")
    ids = {slug: number for number, slug in enumerate(merged.plugs, start=1)}
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        with engine.begin() as db:  # one transaction: all of it or nothing
            if ids:
                db.execute(
                    insert(Outlet),
                    [{"id": ids[s], "slug": s, "name": p.name, "ip": p.ip} for s, p in merged.plugs.items()],
                )
            if merged.hours:
                db.execute(
                    insert(HourlyEnergy),
                    [
                        {
                            "outlet_id": ids[s],
                            "hour_start": start,
                            "kwh": h.kwh,
                            "seconds_covered": h.seconds_covered,
                        }
                        for (s, start), h in sorted(merged.hours.items())
                    ],
                )
            if merged.readings:
                db.execute(
                    insert(Reading),
                    [
                        {"outlet_id": ids[s], "ts": ts, "power_w": power_w}
                        for (s, ts), power_w in sorted(merged.readings.items(), key=lambda item: item[0][1])
                    ],
                )
    finally:
        engine.dispose()


def check_database(path: Path, merged: Merged) -> None:
    """Read the new file back and compare it with what it should hold."""
    with closing(sqlite3.connect(path)) as db:
        integrity = [row[0] for row in db.execute("PRAGMA integrity_check")]
        orphans = db.execute("PRAGMA foreign_key_check").fetchall()
        hours, kwh = db.execute("SELECT COUNT(*), TOTAL(kwh) FROM hourly_energy").fetchone()
        (readings,) = db.execute("SELECT COUNT(*) FROM readings").fetchone()
    expected_kwh = sum(hour.kwh for hour in merged.hours.values())
    if integrity != ["ok"] or orphans:
        raise MergeError("the new database failed SQLite's checks")
    if (hours, readings) != (len(merged.hours), len(merged.readings)) or not isclose(
        kwh, expected_kwh, abs_tol=1e-6
    ):
        raise MergeError("the new database does not hold what was merged")


def merge_databases(output: Path, source_paths: list[Path]) -> Merged:
    """Merge the sources into `output`, which appears only once it is complete and checked."""
    # A leftover -wal or -shm file would be applied to the new database, so they count as existing too.
    for path in (output, Path(f"{output}-wal"), Path(f"{output}-shm")):
        if path.exists():
            raise MergeError(f"{path} already exists; nothing is overwritten")
    merged = combine([read_source(path) for path in source_paths])
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".partial-", dir=output.parent) as work:
        partial = Path(work) / "merged.db"
        write_database(partial, merged)
        check_database(partial, merged)
        partial.rename(output)
    return merged


def describe(merged: Merged, source_paths: list[Path], tz: ZoneInfo) -> list[str]:
    """A report for the person running the merge, with local times."""

    def local(moment: datetime) -> str:
        return moment.astimezone(tz).strftime("%Y-%m-%d %H:%M")

    lines = [
        f"Hours taken from {path}: {count}" for path, count in zip(source_paths, merged.hours_taken, strict=True)
    ]
    lines.append(f"Total: {len(merged.hours)} hourly rows and {len(merged.readings)} readings")
    for slug in merged.plugs:
        starts = sorted(start for s, start in merged.hours if s == slug)
        hours = [merged.hours[slug, start] for start in starts]
        partial = sum(1 for hour in hours if hour.seconds_covered < MIN_TRUSTED_SECONDS)
        lines.append("")
        lines.append(f"{slug}: {len(hours)} hours, {sum(h.kwh for h in hours):.3f} kWh, {partial} partly measured")
        first = 0
        for i, start in enumerate(starts):
            # A stretch ends at the last hour, or before a missing one.
            if i + 1 == len(starts) or starts[i + 1] - start != ONE_HOUR:
                lines.append(f"  {local(starts[first])} to {local(start + ONE_HOUR)}")
                first = i + 1
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.merge", description="Merge databases into a new one.")
    parser.add_argument("output", type=Path, help="the database to create")
    parser.add_argument("sources", type=Path, nargs="+", help="databases to read; on a tie, later ones win")
    args = parser.parse_args(argv)

    tz = ZoneInfo(Settings().timezone)
    try:
        merged = merge_databases(args.output, args.sources)
    except (MergeError, sqlite3.Error, OSError) as exc:
        print(f"Merge failed: {exc}", file=sys.stderr)
        return 1
    print("\n".join(describe(merged, args.sources, tz)))
    print(f"\nSaved: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

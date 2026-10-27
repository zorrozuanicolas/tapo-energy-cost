# 0003. SQLite as the database

- Status: accepted
- Date: 2026-10-27

## Context

This is a monitor for one household: two plugs today, one poller that writes, and a dashboard that reads.
It runs as a single backend container under Docker Compose. Nobody else writes to the data.

The data is time-series: instantaneous power readings, plus hourly energy totals. Raw readings are
deleted after `raw_retention_days` (60 by default), so the table does not grow without bound.

The poller does not exist yet, so the polling interval is a design assumption, not a measurement. With
one reading every 10 seconds per plug, two plugs write about 17,000 rows a day, which is about one
million rows at the 60-day retention limit. That is small for any SQL database.

The author runs this at home and wants it easy to deploy, back up and demo.

## Decision

We will use SQLite in WAL mode, through SQLAlchemy async with the `aiosqlite` driver. The database is
one file in a mounted volume.

- `make_engine` creates the folder and sets four PRAGMAs on every connection: `journal_mode=WAL` (readers
  work while the poller writes), `synchronous=NORMAL`, `busy_timeout=5000` and `foreign_keys=ON`
  (SQLite ignores foreign keys unless asked).
- All access goes through SQLAlchemy, and the URL comes from `Settings.database_url`, so the database
  is chosen by configuration.

## Alternatives considered

- **PostgreSQL**: the right choice with several writers, several app instances, or data that must be
  reachable over the network. Here it would add a second container, credentials, a volume and a backup
  routine, all for one writer and about a million rows. Deferred, not rejected.
- **A time-series database (InfluxDB, TimescaleDB)**: built for write rates far above what a few plugs
  produce. It would add a service and a query language for no gain at this size.
- **Plain files (CSV or JSON)**: no queries, no integrity checks and no safe concurrent access. The
  hourly totals and cost reports need real queries.

## Consequences

- There are no services to run. A backup is a copy of one file, and tests use a temporary file, so they
  need no setup.
- A demo is easy to ship, because the database travels with the app.
- Only one process can write at a time. That is fine while the poller is the only writer, but it rules
  out running several backend instances against the same file.
- The file must be on a local disk. WAL does not work reliably on network shares.
- SQLite cannot alter columns in place, so Alembic runs in batch mode and rebuilds tables when a column
  changes. See [0004](0004-alembic-migrations.md).
- The PRAGMA listener in `make_engine` is SQLite-specific code that would go away with a move.

## Future direction

We expect to move to PostgreSQL if the app needs several users, several backend instances, or remote
access to the data. The move should be cheap: all access goes through SQLAlchemy, so the changes would be
the URL and driver, the PRAGMA listener, and the batch mode setting. Existing data would need a one-time
copy. A new ADR will record that change and supersede this one.

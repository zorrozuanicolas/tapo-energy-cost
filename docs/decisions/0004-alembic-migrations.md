# 0004. Alembic migrations

- Status: accepted
- Date: 2026-10-27

## Context

The schema will change as the project grows, for example when hourly aggregation or retention need new
columns. The tables hold real meter readings that cannot be recreated, so a schema change must not mean
deleting the data.

The database is SQLite ([0003](0003-sqlite-as-the-database.md)), which cannot alter or drop most columns in
place. Any change to an existing table has to rebuild it.

## Decision

We will manage the schema with Alembic, using the async template.

- `migrations/env.py` uses `Base.metadata` as the target, so autogenerate compares the database to the
  models.
- The database URL comes from `Settings.database_url`. `alembic.ini` only holds a placeholder, and a URL
  set beforehand (a test, for example) is kept.
- The engine comes from `make_engine`, so the database folder and the SQLite PRAGMAs are the same as in
  the app.
- `render_as_batch=True` makes Alembic rebuild a table when SQLite cannot do the change directly.
- Migrations are written from autogenerate and reviewed by hand. The initial migration uses
  `sa.DateTime()` instead of the app's `UtcDateTime`, so the migration history does not import app code
  that may change later. Both produce the same column.
- Migrations are applied by hand with `uv run alembic upgrade head` for now. Applying them when the app
  starts belongs to the API milestone.
- A test runs `upgrade head` on an empty database and compares the result with the models. It fails when
  a model changes without a new migration.

## Alternatives considered

- **`Base.metadata.create_all` at startup**: the simplest option, but it only creates missing tables. It
  never changes an existing one, so every schema change would mean deleting the database or editing it by
  hand.
- **Hand-written SQL scripts**: no tooling to learn, but we would have to build our own version tracking
  and downgrade path, which is what Alembic already does.

## Consequences

- Schema changes keep the data, and the history of changes is reviewable in Git.
- Every model change now needs a migration. The schema test catches a forgotten one.
- There are more files to maintain: `alembic.ini`, `migrations/` and the revision files.
- Batch mode rebuilds tables on SQLite. That is fine for this data size, but it is slower than a direct
  `ALTER` and needs care with foreign keys.
- Generated revision files need a ruff cleanup. A `post_write_hooks` entry in `alembic.ini` could do it
  automatically; it is not set up yet.
- Until the API milestone, someone must run `upgrade head` by hand after pulling a change that adds a
  migration.

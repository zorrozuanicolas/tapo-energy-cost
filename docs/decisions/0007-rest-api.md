# 0007. REST API

- Status: accepted
- Date: 2026-11-05

## Context

The frontend (M8-M9) needs to read the aggregated consumption ([0006](0006-cost-on-read-aggregation.md)),
the tariff in force, and the list of plugs. The app is a single process: one SQLite file
([0003](0003-sqlite-as-the-database.md)), one set of YAML files, and later a background poller.

Three things make the shape of the application matter:

- The schema is owned by Alembic ([0004](0004-alembic-migrations.md)), so a new database must be
  migrated before the app can use it.
- Tests need to start the app without reading the real settings, and to control the clock.
- Errors of the domain (a bad range, an unknown tariff date) must reach the client as proper HTTP errors.

## Decision

We will build the API with FastAPI in `app/main.py`.

- **An app factory, with no module-level `app`.** `create_app(settings)` builds the application, and it is
  run with `uvicorn app.main:create_app --factory`. Importing the module reads no settings and touches no
  files.
- **Startup brings the database up to date.** The lifespan first reads the YAML files, so a broken
  configuration stops the app before it touches the database. Then it runs `alembic upgrade head`
  (`upgrade_database_async`), creates the engine and syncs the outlets. The upgrade runs in a worker
  thread, because `migrations/env.py` calls `asyncio.run`, which cannot run inside a running event loop.
  `env.py` also keeps existing loggers (`disable_existing_loggers=False`), or the app's own logs would be
  silenced.
- **One typed state, typed dependencies.** Everything the endpoints need (settings, time zone, billing
  configuration, outlets, session factory) lives in a frozen `AppState` built once at startup. Endpoints
  receive it through `Annotated` dependencies (`StateDep`, `SessionDep`, `NowDep`), not by reading
  `request.app.state` themselves, so mypy can check them and tests can override them.
- **The clock is a dependency** (`get_now`). "Today" and the `partial` flag are computed from it, so tests
  fix the time instead of depending on the real one.
- **Domain errors become HTTP in the endpoint**: `RangeError` is a 400 with its message, a date before the
  first tariff is a 404, and malformed parameters are a 422 from FastAPI itself.
- **Read-only.** Only `GET`, and CORS allows only the origins in `cors_origins` (the Vite dev server by
  default). In production one server serves both the frontend and the API, so CORS is not needed there.
- **Endpoints**:
  - `/api/health`: status and the configured outlets.
  - `/api/outlets`: the configured outlets, in order.
  - `/api/range`: the first local day with data, so the history navigator knows how far back it can go.
  - `/api/tariff?date=`: the tariff in force on a local date (today by default).
  - `/api/consumption?granularity=&from=&to=`: the aggregation of 0006.

  The live stream (`/api/live`) and the online state of each plug come with the poller (M6).

## Alternatives considered

- **A module-level `app = create_app()`**, as in the first version: simpler to run, but importing the
  module reads the real settings and files, which makes tests depend on the environment.
- **`Base.metadata.create_all` at startup**: it would work for an empty database but ignores Alembic's
  history, so the two would disagree after the first schema change.
- **Running the migrations only by hand**: one command less in the code, but a fresh container would fail
  until someone ran it.
- **Reading `request.app.state.x` in each endpoint**: less code, but untyped and harder to override in
  tests.
- **Letting the frontend work out the tariff**: the API already knows the tariff and the VAT, so the rates
  with VAT are sent ready to use.

## Consequences

- The README must document the `--factory` command when the project is runnable end to end.
- A second process on the same SQLite file would race on the migration. That is fine for the planned
  single-container deployment.
- Tests start the app in-process with `httpx` and a temporary database, with no real server or port. A real
  `uvicorn` run (sockets, signals) is not covered by them.
- The JSON keys of `outlets` and `totals` are outlet ids as strings (see 0006).
- Anyone running a frontend from another origin must add it to `CORS_ORIGINS`.

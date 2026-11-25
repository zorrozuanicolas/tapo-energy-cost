# 0014. Docker deployment

- Status: accepted
- Date: 2026-11-25

## Context

The app is meant to run unattended at home, on a Raspberry Pi (ARM) or a PC (x86), and someone who just cloned the
repository should be able to try it with one command and no hardware. It has a poller that must keep measuring, an
SQLite file that must survive updates, and the credentials of a Tapo account. The built frontend is a set of static
files that need a web server, and the Vite dev proxy for `/api` does not exist after the build
([0012](0012-frontend-stack.md)).

## Decision

We will run the app with Docker Compose, as two containers.

- **`frontend`: nginx serves the built dashboard and forwards `/api` to the backend.** It is the only published port
  (8080 by default), so the browser sees one origin and no CORS setup is needed. It looks the backend's name up
  again every 10 s, so a recreated backend with a new address does not need an nginx restart. It does not buffer the
  live stream because the backend asks for that (`X-Accel-Buffering: no`), and the stream's keepalive every 15 s is
  well within nginx's 60 s read timeout.
- **Caching:** files under `/assets/` have a content hash in their names and are cached for a year; the rest must be
  revalidated.
- **`backend`: one uvicorn process,** because the live stream keeps its state in memory
  ([0009](0009-live-stream.md)). Dependencies are installed from `uv.lock` in a build stage, and `uv` is not in the
  final image.
- **Neither container runs as root.** The backend runs as user 1000, which can write only to the data folder.
- **State and settings stay outside the images.** The database is in `./data`, `./config` is mounted read-only, so
  tariffs and plugs change with a restart, and secrets come only from a `.env` file at the repository root. That file
  is optional: without it the plugs are fake.
- **Time zone:** one `TIMEZONE` value configures the backend and is built into the dashboard.
- **Shutdown:** an open live stream never ends by itself. uvicorn cuts open connections after 2 s and then closes the
  database; without that limit Docker kills the process first. Docker is told to wait 10 s. nginx is stopped at once
  (`SIGTERM`), as it stores nothing.
- **CI starts the whole app with mock plugs,** checks the page, the API and the live stream through nginx, checks
  that the backend stops cleanly with a stream open, and builds both images for ARM.

## Alternatives considered

- **One container, with FastAPI serving the built files**: one thing less to run and no `nginx.conf`, but more Python
  code (files and cache headers) with its tests, an image that needs Node and Python to build, and every change to the
  dashboard would restart the poller. For one household both would perform well enough.
- **Installing with `pip` from `pyproject.toml`** (the old app): it ignores the lock file, so two builds can get
  different versions.
- **Publishing the backend's port too**: handy for the interactive docs, but a second way in, and the API is already
  reachable under `/api`.
- **A Docker-managed volume for the database**: no permission step on Linux, but the file is harder to find, copy
  and back up.
- **Building the images in CI and pulling them from a registry**: faster updates on the Pi, but it adds a registry,
  credentials and a release step that nothing needs yet.
- **The official nginx image**: it starts as root.

## Consequences

- There is no login. Anyone who can reach port 8080 can read the data, so it belongs on a home network until access
  control is added in front of it.
- The interactive API reference (`/docs`) is not reachable through nginx.
- The machine that runs the app builds its own images, which takes a while on a Raspberry Pi.
- On Linux, `data/` must exist and belong to user 1000 before the first start.
- Changing `TIMEZONE` needs a rebuild.
- Fake and real readings go to the same file, `data/tapo.db`. Delete it before changing from mock plugs to real ones.
- An open dashboard at shutdown leaves a `CancelledError` traceback in the backend's log, followed by
  `Application shutdown complete`. It is expected.
- Each container keeps at most three log files of 10 MB, so old lines are discarded. The logs also belong to the
  container: recreating it, for example on an update, discards them all.
- The images were tested on Docker Desktop (x86), and the ARM ones only under emulation. Nothing has run on a real
  Raspberry Pi yet, and no container has talked to a real plug.

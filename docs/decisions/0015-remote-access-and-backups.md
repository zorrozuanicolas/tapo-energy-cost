# 0015. Remote access and backups

- Status: accepted
- Date: 2026-11-25

## Context

Two needs remain after [0014](0014-docker-deployment.md).

- **Looking at the dashboard away from home.** The machine sits behind a home router, and the app has no login.
- **Not losing the history.** Everything is in one SQLite file. The plugs keep only about a week of hourly energy
  ([0010](0010-pruning-and-backfill.md)), and the previous version of this project lost its machine's disk (the
  disk or its USB adapter failed).

## Decision

**Remote access: an optional Cloudflare Tunnel, protected by Cloudflare Access.**

- A `cloudflared` container, in the Compose profile `tunnel`, so nothing connects outside unless asked to.
- It connects outwards, so the router needs no open port, and it forwards to nginx. One address serves the page and
  the API, which the Access login needs: its cookie belongs to one hostname.
- Authentication happens in Cloudflare, before a request reaches home. The app still has no login of its own.
- The token comes from `.env`. The backend, which reads that file too, gets an empty value in its place.

**Backups: a command in the backend, `python -m app.backup`.**

- It uses SQLite's online backup, so it is safe while the poller writes, and opens the database read-only.
- The copy must pass `PRAGMA integrity_check` before it is compressed and given its final name, so neither a damaged
  database nor an interrupted run leaves a file that looks like a good backup.
- Backups older than 14 days (`--keep-days`) are deleted, only after a new one succeeded. Their age comes from
  the date in the name, so copying a file does not change it. Other files are left alone.
- `scripts/backup.sh` runs it in the running container, for a person or for cron. Restoring is a documented manual
  step.

## Alternatives considered

- **Home network only**: the safest and simplest, but no access from outside. It remains the default.
- **Tailscale or another VPN**: private to the owner's devices and needs no domain, but every device needs the
  client installed and signed in.
- **Opening a router port**: no third party, but the app would need its own login and HTTPS first.
- **A login inside the app**: security code to write and keep up to date, for a single user.
- **Copying the database file**: rows still in the `-wal` file are missed, and a copy taken during a write can be
  corrupt.
- **A shell script with an embedded Python program** (the old app): no lint, type check or tests.
- **Scheduling backups inside the app**: it would make backups depend on the app being healthy, for something cron
  already does.

## Consequences

- Cloudflare decrypts the traffic on its way, so it can read it, and remote access depends on its service and on a
  domain.
- The protection is a setting outside this repository: without an Access application, the tunnel publishes the app to
  anyone.
- Backups are on the same disk as the database. They protect against mistakes and a damaged database, not against
  losing the disk: that needs a copy on another machine, which is manual for now.
- Nothing warns when a scheduled backup fails; its output goes to a log file.
- A run interrupted by a power cut can leave a `.partial-*` folder in the backups folder, safe to delete.
- Backups are not encrypted.
- The tunnel was tested only with an invalid token. A real connection is still to be checked.

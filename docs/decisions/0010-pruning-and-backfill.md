# 0010. Pruning and backfill

- Status: accepted
- Date: 2026-11-12

## Context

The app is meant to run unattended for months, and two things go wrong over time.

- **Raw readings never stop growing.** The poller ([0008](0008-plug-clients-and-poller.md)) stores a reading every
  10 s, about 8,600 rows per plug per day. The hourly energy is what the history views use, so old raw readings
  are only dead weight.
- **The hourly energy has holes.** The app knows nothing from before its first start, and an outage (a reboot, a
  Wi-Fi drop) leaves hours missing or only partly measured ([0005](0005-energy-integration.md) skips the energy
  of a gap on purpose). The plug itself keeps about a week of hourly energy, in whole Wh.

## Decision

We will delete old raw readings on a schedule, and fill the hourly energy from the plugs' own history.

**Pruning**

- Every 6 hours, delete the `Reading` rows older than `RAW_RETENTION_DAYS`. A reading exactly at the limit is kept.
- `HourlyEnergy` is never deleted, so history and costs do not change.
- It runs even when the poller is off, because it only touches the database.

**Backfill**

- At startup and then every 6 hours, ask each plug for its last 8 days of hourly Wh (today and the 7 days before
  it, the most a plug answers), one plug at a time, with a 30 s timeout. A plug that fails or does not answer is
  logged and skipped, and the next round tries again.
- **The merge rule.** The plug's figures are whole Wh, while the poller's are finer.
  - An hour with no row is inserted, marked as fully covered (`seconds_covered = 3600`).
  - An hour the poller covered for at least 90% (3240 s) is left alone.
  - An hour the poller covered for less is replaced by the plug's total, and marked as fully covered. That makes
    running the backfill again harmless: the hour is now trusted and is not touched.
- Zeros before the first non-zero hour mean "the plug had no history yet", not real zero consumption, so they are
  skipped. The current hour is skipped too: it is still in progress and belongs to the poller.
- Entries with the same start time (a clock change can produce them) are added up.
- **The time zone does not matter for storage.** From `tapo` 0.12.2 the library reads the requested dates in the
  plug's own time zone, whatever the host's is, and each entry's start comes back in UTC, which is how we store
  it. The old app checked the history against the plug's `today_energy` and set the process `TZ`; neither is
  needed now.
- The backfill runs only when the poller is on, because it needs the plug clients. It shares the poller's clients,
  so the two take turns on each plug's lock and never log in at once.

Both loops run under `supervise` ([0008](0008-plug-clients-and-poller.md)), so an unexpected error restarts them.
The intervals and the timeout are module constants, not settings.

## Alternatives considered

- **Never overwrite an hour that has a row** (the old rule): the simplest, but an hour the poller measured only
  partly stays under-counted for good, although the plug has the full figure.
- **Always use the plug's figure**: it loses the poller's finer data for hours it measured well.
- **Keep the alignment check and the `TZ` change from the old app**: they guarded against a problem the library
  no longer has, and the check could reject correct data when the plug's time zone differs from ours.
- **Settings for the intervals**: more to document and test, with no use for them yet. A constant is easy to turn
  into a setting later.
- **Backfill all plugs at the same time**: faster, but a burst of logins on the network for a job that runs
  rarely.
- **A job outside the app (cron)**: one more thing to deploy, and it could not share the plug clients' locks.

## Consequences

- Replacing a poorly covered hour trades the poller's finer data for a whole-Wh figure, with up to 0.5 Wh of
  rounding per hour. `seconds_covered` is the only signal used to decide.
- The plug keeps only about a week. An outage longer than that leaves a permanent hole.
- Deleting readings cannot be undone. The delete filters by time only, so it does not use the
  `(outlet_id, ts)` index. At this size that does not matter.
- With `POLLER_ENABLED=false` nothing talks to the plugs, so nothing is imported.
- The tests cover the merge rule, the schedules, the failure handling and the wiring with fake plugs. The real
  `get_energy_data` call is not covered: it needs a manual check with a real plug, never while another machine
  polls the same plug.

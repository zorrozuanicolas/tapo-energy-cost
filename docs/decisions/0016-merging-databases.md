# 0016. Merging databases

- Status: accepted
- Date: 2026-11-25

## Context

Separate installations that read the same plugs, including the predecessor of this app, left separate databases.
Their histories overlap in places, because each one imported about a week from the plugs when it started
([0010](0010-pruning-and-backfill.md)). The plugs keep no more than that, so these files are the only copy of the
older history. The predecessor's schema differs a little (an extra column, no Alembic table).

## Decision

We will merge them into a new database with a command in the backend:

```sh
uv run python -m app.merge OUTPUT SOURCE [SOURCE ...]
```

- **The sources are opened read-only,** each read in one transaction, so a database in use can be read and none is
  changed.
- **Nothing is overwritten.** The command stops if the output, or a `-wal` or `-shm` file of that name, exists.
- **Plugs are matched by slug,** because ids belong to each database. The last source describes each plug's name and
  address.
- **For an hour in several sources, the row covering more of it wins,** and on a tie the source listed later. It is the
  same idea as the backfill: the more complete measurement is the better one.
- **Raw readings are combined,** storing a plug and instant once.
- **The output gets the current schema from the migrations,** is read back and compared (integrity, foreign keys, row
  counts, total kWh), and only then gets its name.
- It prints a report: rows taken from each source, and each plug's kWh and stretches of data in local time.

To switch the app to the result: stop the app, merge, review the report, point `DATABASE_URL` to the new file and
start the app again. The app must be stopped for this final run, or what it records afterwards stays behind.

## Alternatives considered

- **Inserting into one of the existing databases**: one file less, but a mistake would damage a history that cannot be
  rebuilt.
- **Adding up the kWh of the same hour**: two sources measured the same energy, so it would be counted twice.
- **Always preferring the newest source**: an hour the newest one saw for five minutes would replace a full one.
- **A one-off script outside the repository**: quicker, but untested, for data that cannot be recovered.

## Consequences

- Two partial rows for one hour are not combined, even if they covered different minutes: one of them is chosen.
- Hours that no source covers stay missing.
- Only the two schemas met so far are known to work.
- Old raw readings in the result are removed by the app's usual pruning.

# 0005. Energy integration

- Status: accepted
- Date: 2026-11-04

## Context

A plug reports instantaneous power in watts, about once every 10 seconds. The tariff has three price
bands that depend on the hour of the day ([0002](0002-versioned-tariffs-in-yaml.md)), so what we need is
energy in kWh per clock hour, not a stream of power samples.

Raw readings are deleted after `raw_retention_days` ([0003](0003-sqlite-as-the-database.md)). The hourly
totals are kept forever, so they must hold everything the cost calculation needs.

The poller can also be off: the app restarts, the network drops, the plug reboots. After such an outage we
do not know what the plug was doing.

## Decision

We will turn each new sample into energy as it arrives (`record_sample` in `app/energy.py`).

- **Store kWh, not money.** Cost is computed when it is read, with the tariff in effect at that time. A
  tariff change then never invalidates stored data.
- **Trapezoid rule.** The energy between two consecutive samples is the average of their two powers
  times the elapsed time.
- **Split at UTC hour boundaries.** An interval that crosses an hour boundary is cut into one piece per
  hour. Each piece is added to its `HourlyEnergy` row with an atomic upsert
  (`INSERT ... ON CONFLICT DO UPDATE`), so there is no read-then-write race. Hours are UTC; mapping an
  hour to a band happens on read, in the local time zone.
- **Gap rule.** An interval longer than `max_gap_seconds` (60 by default, about six polls) adds no
  energy. The raw reading is still stored. A hole is better than invented energy.
- **`seconds_covered` is a whole number.** The rounded running total is split across the pieces of an
  interval, so they add up exactly to the rounded length of the interval. kWh uses the exact seconds, so
  rounding never affects it.
- **`record_sample` does not commit.** The caller (the poller) owns the transaction, so a reading and
  its energy are saved together or not at all.

## Alternatives considered

- **Hold the last value (rectangle rule)**: simpler, but biased when power changes between two samples.
  The trapezoid costs one extra addition.
- **The plug's own energy counter**: not used for now. It restarts when the plug reboots and its
  resolution is coarse. The backfill milestone may use the plug's stored history to fill holes.
- **Filling gaps by interpolation**: it would add energy we never measured.
- **Storing cost in the hourly table**: it would freeze today's tariff into old rows.
- **A float `seconds_covered`**: exact, but it needs a migration for no real gain, because the column is
  informational.

## Consequences

- A real outage leaves a visible hole, and `seconds_covered` shows how much of each hour has data.
- `max_gap_seconds` must stay a few times the polling interval. If the interval grows, the limit must
  grow with it.
- `add_energy` uses the SQLite-specific `INSERT ... ON CONFLICT`. A move to PostgreSQL would have to
  change it, as noted in 0003.
- The trapezoid rule is tested against hand-computed values, not against real plug data.

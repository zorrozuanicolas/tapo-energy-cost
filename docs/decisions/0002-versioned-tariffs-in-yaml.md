# 0002. Versioned tariffs and holidays in YAML

- Status: accepted
- Date: 2026-10-26

## Context

UTE's Plan Inteligente Hogares has three price bands (valle, llano, punta). Prices, VAT and the
punta window change over time, and UTE publishes a new holiday list every year. Punta does not
apply on weekends or holidays. Costs already computed for past months must not change when
new prices are published.

Both files change about once a year, and each change is a small edit: a new tariff entry, or a
holiday block copied from UTE's published list.

## Decision

We will keep prices and holidays in two YAML files under `config/`, outside the code.

- `tariffs.yaml` is a list of entries, each with a `valid_from` date. An entry applies until the
  next one starts. A price change means adding an entry, never editing an old one.
- `holidays.yaml` maps each year to its weekday holidays. Weekends are handled in code.
- Loaders validate both files at startup and raise a `ConfigError` that names the file and
  entry. The app does not start with a broken configuration.
- Band lookup is a pure function of a timezone-aware local datetime and a tariff. A naive
  datetime is rejected, because its hour cannot be trusted to be local.

## Alternatives considered

- **Constants in code**: every price change would need a code change and a release.
- **Database tables**: scales better if tariffs must be edited from the app or by several
  users. Deferred, not rejected: today it would add a schema, migrations and an editing UI
  for a few rows a year, and price changes would no longer be recorded as reviewable
  commits in Git. See "Future direction" below.
- **One mutable tariff**: simpler, but editing a price would silently recalculate the whole
  history with the wrong prices.
- **Fetching holidays from an external API**: adds a network dependency and a failure mode for
  data that changes once a year.

## Consequences

- Past costs stay correct, and the price history is visible in Git.
- Someone must add a new holidays block each year. A missing year is detectable with
  `has_holidays_for`, so the app can show a warning instead of billing wrongly.
- Changing prices needs a file edit and a restart, not a UI. For one edit a year this is
  cheaper than building and maintaining an editing UI.
- Valle (00:00-07:00) is fixed in code. If UTE changes it, that is a code change.

## Future direction

We expect to move tariffs and holidays into the database when editing them from the app
becomes a requirement. The move should be cheap: the loaders already return plain `Tariff`
and holiday objects, so only the loading code changes, not `BillingConfig` or `band_for`.
A new ADR will record that change and supersede this one. It would also need its own
history of changes, such as an audit table, to keep what Git gives us today.

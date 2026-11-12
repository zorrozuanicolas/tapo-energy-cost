# 0011. Demo seed

- Status: accepted
- Date: 2026-11-12

## Context

On a fresh checkout the history views (the day and month charts, the costs) are empty. Real history takes weeks
to build, and the fake plugs ([0008](0008-plug-clients-and-poller.md)) only produce live readings. A reviewer, or
someone visiting a hosted demo, needs data to look at without owning any Tapo plug.

## Decision

We will let the app create fake hourly history at startup, controlled by one setting.

- **`SEED_DEMO_DAYS=N`** creates N days of fake hourly energy, ending at the last completed hour. The default is 0
  (off) and the most is 1100, so a typo cannot build a huge history in memory.
- **It only writes into an empty `HourlyEnergy` table.** The check is inside `seed_demo`, not in the code that
  calls it, so the function cannot be used in a way that mixes fake hours with real ones. A second start finds
  data and does nothing, whatever N is.
- **It needs fake plugs.** `SEED_DEMO_DAYS` above 0 with `TAPO_MOCK=false` is refused at startup, whether or not
  the poller is on. Fake history in a database that real plugs write to could never be told apart again.
- **It is deterministic.** The random generator has a fixed seed, so a demo looks the same on every start and the
  tests can assert exact values.
- **The shapes are realistic.** The first plug behaves like a fridge: steady, with the odd harder-working hour. The
  others behave like a desk: busy on business days, with some evening use on days off. Business days come from
  the same `BillingConfig` that prices the energy, so a weekday holiday behaves like a day off.
- **The rows look like any full hour:** aware UTC, `seconds_covered = 3600`. The seed stops before the current
  hour, which belongs to the poller. The fake plugs have no history of their own
  ([0010](0010-pruning-and-backfill.md)), so the backfill and the seed do not touch each other.
- **It runs in the lifespan, before any background task starts,** so none of them sees a half-filled table. There
  is no separate command.

## Alternatives considered

- **A command-line script** (the old app had one): one more entry point, with argument parsing, for something the
  environment variable already does.
- **Seeding in a migration**: migrations describe the schema, and this would put fake data in real databases.
- **Different random data on each start**: demos that change every time, and tests that cannot assert values.
- **A static JSON file for the hosted demo**: it needs no backend, but it would not show the real queries and
  pricing. This stays open for the deployment milestone.
- **Allowing the seed with real plugs through an override flag**: one more flag to explain, for a case nobody needs.
  Deleting the database file and starting again does the job.
- **Topping up missing days on every start**: harder to get right and to explain, and there is no use for it.

## Consequences

- The demo data is fake. The costs and charts built from it say nothing about real consumption.
- The seed builds all its rows in memory before writing them, which is why the number of days has a limit.
- The tariffs apply to the seeded dates as usual. A seed that reaches back before the first tariff in
  `tariffs.yaml` makes the API show its "no tariff" warning, and holidays missing from `holidays.yaml` count as
  ordinary weekdays.
- The app cannot tell a seeded database from a real one afterwards. Do not point real plugs at it.
- The tests cover the shapes, the empty-table rule, the limits of the setting, the guard and the startup. They do
  not check the data by eye in a browser.
- The hosted demo itself is not designed here. It will build on this seed and get its own decision.

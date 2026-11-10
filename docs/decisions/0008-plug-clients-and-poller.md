# 0008. Plug clients and the poller

- Status: accepted
- Date: 2026-11-10

## Context

The app needs a power reading from every plug every few seconds, to build the energy history
([0005](0005-energy-integration.md)). The plugs make this harder than it looks:

- They go offline (power cut, Wi-Fi, firmware update), and nothing should be invented for those periods.
- A plug rejects two logins at the same time.
- Two machines polling the same plug fight over the login. In particular, a development PC must not poll
  the plugs while the Raspberry Pi already does.
- Development and CI have no plugs at all.

The readings must also reach the browsers live, without a slow browser ever delaying the polling.

## Decision

We will read the plugs from a background task inside the API process, in `app/clients.py`,
`app/poller.py`, `app/live.py` and `app/supervisor.py`.

- **`OutletClient` is a `Protocol` with one method**, `read_power_w()`, with a mock and a Tapo
  implementation. The poller depends on the interface, never on the `tapo` library. The library is
  imported only when a real client is built, so mock mode and CI never load it.
- **Mock plugs are the default** (`TAPO_MOCK=true`). A fresh checkout can never touch real hardware, which
  also guards the "PC and Pi polling at once" case. Real mode needs `TAPO_USERNAME` and `TAPO_PASSWORD`,
  and the settings refuse to load without them, so a mistake shows at startup and not on the first poll.
  The password is a `SecretStr`, kept out of `repr()` and logs.
- **10 s polling.** `max_gap_seconds` must be at least twice `poll_interval_seconds`, which the settings
  enforce. One missed poll then still counts as continuous, while a real outage does not.
- **An outage is never bridged.** When a read fails, the poller forgets that plug's previous sample, so the
  first sample after the outage adds no energy, even if the gap is within `max_gap_seconds`. The same
  applies when storing a sample fails.
- **The poller owns the transaction.** It saves each reading and its energy in one commit
  (`record_sample` does not commit, see 0005). A failure on one plug, whether reading, timeout or storing,
  is logged and never stops the other plugs or the loop. A read times out after the polling interval (at
  most 20 s), so a stuck plug cannot overlap the next round.
- **A round reads all plugs concurrently** (`asyncio.gather`), so a slow plug does not delay the others.
- **One lock per Tapo client**, because the plug rejects two simultaneous logins. After any error the
  client drops its connection and logs in again on the next read.
- **Failures are logged sparingly**: the first one and then one in twenty, plus one message when the plug
  is back.
- **`LiveHub` is an in-memory fan-out.** It keeps the latest reading of each plug and gives every
  subscriber a bounded queue. `publish` never waits: a full queue means that browser misses an update, and
  the next one carries fresh data.
- **The task is supervised.** `supervise` restarts it after a crash (logging the traceback) or an
  unexpected return. On shutdown the lifespan cancels it and waits for it **before** closing the database it
  writes to. `POLLER_ENABLED=false` runs only the API.

## Alternatives considered

- **A separate poller process or container**: isolates failures, but needs a second deployment and cannot
  share the in-memory hub, so the live view would need a broker.
- **A message broker between poller and browsers**: far too much for a single process and a few plugs.
- **One task per plug**: independent timing, but more tasks to supervise and a harder test setup. A single
  round with `gather` has the same isolation.
- **Polling inside request handlers**: no continuous history when nobody has the page open.
- **Integrating across short outages**: it would fill small holes, but it would invent energy whenever the
  plug was actually off. The plug's own hourly history (M7) is the honest way to fill them.
- **Mock only when no credentials are set**: convenient, but a typo in a variable name could silently
  switch real plugs to fake data, or the reverse. An explicit `TAPO_MOCK` flag leaves no doubt.

## Consequences

- While the app is down nothing is collected. M7 will import the plugs' own hourly history to fill those
  hours.
- Only one machine may run with `TAPO_MOCK=false` against the same plugs. Nothing in the code can enforce
  that: it is a rule for whoever deploys.
- Readings that reach the live view but fail to be stored are visible to the user and absent from the
  history. The log shows it.
- Restarting the app loses the previous samples held in memory, so the first reading after a restart adds
  no energy. That is the same rule as an outage.
- The `SecretStr` hides the password from logs but does not encrypt it: it still lives in the `.env` file.
- Tests use fake clients, a hand-moved clock and a temporary database. A real plug is never needed, but the
  real `tapo` calls are covered only by the fake's assumptions (milliwatts from `get_energy_usage`, watts
  from `get_current_power`), so they need a manual check with a real plug.
- The app's own logs (`tapo.*`) follow `LOG_LEVEL`, set at startup by `configure_logging`. uvicorn and
  alembic keep their own logging setup, so the level does not change their output.
- The SSE endpoint that serves the hub to browsers is decided separately, with PR B.

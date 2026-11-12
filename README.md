# tapo-energy-cost

Measures how much energy the appliances plugged into TP-Link Tapo P110/P115 smart plugs use, and
calculates what that energy costs under UTE's *Plan Inteligente Hogares* (Uruguay's three-band
time-of-day tariff: Valle, Llano and Punta).

> 🚧 **Work in progress.** This project is being rebuilt step by step, with every design decision
> documented.

## Running the backend

You need Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```sh
cd backend
uv sync                 # install the dependencies
uv run pytest           # run the tests
uv run uvicorn app.main:create_app --factory
```

The app is built by `create_app()` and there is no module-level `app`, so `--factory` is required
([why](docs/decisions/0007-rest-api.md)). On the first start it creates `backend/data/tapo.db` and applies the
database migrations by itself. The plugs are listed in [`config/outlets.yaml`](config/outlets.yaml).

By default the plugs are **fake** (`TAPO_MOCK=true`): nothing touches the network or a real plug, so you can try
everything without hardware. Once it is running:

- `GET /api/health` and `GET /api/outlets`: the configured plugs.
- `GET /api/live`: a stream of live power readings (`curl -N http://127.0.0.1:8000/api/live`).
- `GET /api/consumption?granularity=day&from=2026-11-01&to=2026-11-08`: energy and cost per plug.
- `GET /api/tariff`: the tariff in force today.
- `/docs`: the interactive API reference.

### Using the real plugs

Copy `backend/.env.example` to `backend/.env` (it is ignored by git) and set:

```
TAPO_MOCK=false
TAPO_USERNAME=<your Tapo account>
TAPO_PASSWORD=<its password>
```

> **Only one machine may poll the same plugs.** Do not run in real mode on your PC while another machine, such
> as a Raspberry Pi, is already polling them.

On startup, and then every 6 hours, the app also imports each plug's own hourly history (about a week), which
fills the gaps left by outages. Raw readings older than `RAW_RETENTION_DAYS` are deleted; the hourly totals are
kept ([why](docs/decisions/0010-pruning-and-backfill.md)).

Set `POLLER_ENABLED=false` to run only the API, without reading any plug. Every setting is documented in
[`backend/.env.example`](backend/.env.example), and the reasoning behind the design is in
[`docs/decisions/`](docs/decisions/).

## License

[MIT](LICENSE) © 2026 Nicolás Zorrozúa

# tapo-energy-cost

Measures how much energy the appliances plugged into TP-Link Tapo P110/P115 smart plugs use, and
calculates what that energy costs under UTE's *Plan Inteligente Hogares* (Uruguay's three-band
time-of-day tariff: Valle, Llano and Punta).

> 🚧 **Work in progress.** This project is being rebuilt step by step, with every design decision
> documented.

## What it looks like

Three tabs (today, week and month) show what each plug used and cost, a chart of the consumption by hour, day or
month with the cost of each bar in a tooltip, and what each plug is drawing right now. The screenshots use fake plugs
and demo data.

![Today: summary cards with live power, the hourly chart with a tooltip, and the table per plug](docs/images/dashboard-today.png)

![Month: twelve months of consumption, with the selected month described in the cards and the table](docs/images/dashboard-month.png)

## Running with Docker

The quickest way to run the whole app. You need Docker with Compose.

```sh
docker compose up -d --build     # then open http://localhost:8080
docker compose ps                # is it running and healthy?
docker compose logs --since 24h backend
docker compose down              # stop it; the data stays in ./data
```

On Linux, such as a Raspberry Pi with a 64-bit OS, create the database folder first. The app runs as user 1000, which
must own it:

```sh
mkdir -p data && sudo chown 1000:1000 data
```

Without any configuration the plugs are **fake**. To change that, copy [`.env.example`](.env.example) to `.env` in the
root folder (it is ignored by git):

- **Demo data:** set `SEED_DEMO_DAYS=30`. It only fills a database with no energy data yet.
- **Real plugs:** set `TAPO_MOCK=false`, `TAPO_USERNAME` and `TAPO_PASSWORD` (keep the password in single quotes).
  Fake readings are stored in the same database, so if you tried the app with fake plugs, stop it and delete `data/`
  first.

> **Only one machine may poll the same plugs.** Do not run in real mode on your PC while another machine, such
> as a Raspberry Pi, is already polling them.

| After changing | Run |
|---|---|
| `.env` | `docker compose up -d` |
| `TIMEZONE`, or the code (after `git pull`) | `docker compose up -d --build` |
| A file in `config/` | `docker compose restart backend` |

Only the dashboard's port is published, and **there is no login**: keep it on your home network. The reasoning behind
this setup is in [0014](docs/decisions/0014-docker-deployment.md).

The two sections below run each part without Docker, for development. They use their own settings file
(`backend/.env`) and database.

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

The history views are empty on a fresh database. To try them, start the app with `SEED_DEMO_DAYS=30` for 30 days of
fake hourly data. It only fills a database with no energy data yet, and it needs the fake plugs
([why](docs/decisions/0011-demo-seed.md)).

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

## Running the frontend

You need Node 22 (the version is in [`frontend/.nvmrc`](frontend/.nvmrc)) and the backend running on port 8000.

```sh
cd frontend
npm ci                  # install the dependencies from package-lock.json
npm run dev             # the app at http://localhost:5173
npm test                # run the tests
npm run check           # lint, format and import order (Biome)
npm run build           # type check (strict) and production build
```

The dev server forwards `/api` to the backend, so no CORS setup is needed. To see the screen with no real plug,
start the backend with its defaults (fake plugs) and `SEED_DEMO_DAYS=30`, as described above. If the API is on
another address, or the plugs are in another time zone, copy [`frontend/.env.example`](frontend/.env.example) to
`frontend/.env.local` and set `VITE_API_URL` or `VITE_TIMEZONE`. The reasoning behind the screen is in
[0013](docs/decisions/0013-dashboard-views.md).

## License

[MIT](LICENSE) © 2026 Nicolás Zorrozúa

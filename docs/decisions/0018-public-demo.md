# 0018. Public demo

- Status: accepted
- Date: 2026-11-26

## Context

People should be able to see and try the dashboard without hardware, installing anything or access to the real one.
The app needs a backend that runs all the time: it polls every few seconds, keeps a live stream open and writes to a
SQLite file ([0008](0008-plug-clients-and-poller.md), [0009](0009-live-stream.md),
[0003](0003-sqlite-as-the-database.md)). The demo must have no connection to the real installation.

## Decision

We will publish a **demo build of the frontend that has no backend**, on Vercel, at `tapo.zorrozuanicolas.com`.

- `npm run build:demo` sets `VITE_DEMO=true` (`frontend/.env.demo`). In that build, the three requests the dashboard
  makes and the live stream are answered by `frontend/src/demo/`.
- The data is made up in the browser: two fictional plugs, a history from the start of the first tariff, and live
  readings every 3 s. An hour's value is calculated from the plug and the hour, so reloading does not change the past
  and nothing is stored.
- Bands, prices and totals follow the backend's rules, rewritten in TypeScript. The tariffs and holidays are copied
  into the demo, and a test fails if the copy differs from `config/`.
- The screens are the same ones, and show a notice that the data is an example.
- The condition `import.meta.env.VITE_DEMO === "true"` is written where it is used. Vite replaces it while building,
  which leaves the demo code out of a normal build; behind a shared function it stayed in.
- CI builds the demo as well as the normal app.

## Alternatives considered

- **Vercel with a real backend with fake plugs on a second host**: shows the whole app running, with little new code,
  but it is a second service to pay for or keep awake.
- **The Raspberry Pi serving a second instance**: it would expose the home machine to the public.
- **The backend as serverless functions**: it would need another database and another way to poll and stream.
- **Saved answers from the real backend as static files**: no pricing code in the frontend, but the dates would grow
  old.

## Consequences

- The demo opens at once and needs no server to look after.
- The pricing rules now exist twice. The tests catch a difference in tariffs or holidays, but a change to the rules
  must be made in both places. Once, on the same 15,824 hourly rows and nine ranges, the demo's answers matched the
  backend's; no test repeats that comparison.
- The demo shows the interface, not the backend.
- It is public: anyone with the address can see it and read its JavaScript. It holds no real data or secrets.
- It uses Montevideo's time zone only.
- From 2027 it warns about missing holidays until they are added to `config/` and to the demo, as the app does.

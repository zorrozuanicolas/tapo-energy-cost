# 0009. Live stream

- Status: accepted
- Date: 2026-11-10

## Context

The browser should show the power of each plug as it changes, a new value every few seconds. The poller
([0008](0008-plug-clients-and-poller.md)) already keeps the latest reading of each plug in an in-memory hub.
The data only flows from the server to the browser: the browser never sends anything back.

The history of past consumption has its own REST endpoints ([0007](0007-rest-api.md)). This decision is only
about the "right now" view.

## Decision

We will serve the live readings with Server-Sent Events (SSE) on `GET /api/live`.

- **One event per reading.** Each event is a `data:` line with JSON shaped by the `LiveOut` schema:
  `outlet_id`, `power_w` (null when the plug cannot be read), `online`, and `ts` in UTC.
- **The snapshot comes first.** A new browser immediately receives the latest reading of every plug, so it
  does not wait up to one polling interval for data. The stream subscribes to the hub **before** taking the
  snapshot, so a reading published in between is not lost. At worst it is sent twice, which is harmless.
- **A keepalive comment every 15 s** when nothing arrives. Browsers ignore comment lines, but proxies see
  traffic and do not close the idle connection (nginx does after 60 s by default).
  `X-Accel-Buffering: no` stops nginx from holding events back, and `Cache-Control: no-cache` stops caches
  from storing the stream.
- **The stream logic is an async generator, `live_events`, and the endpoint only wraps it.** The generator
  has a `finally` that unsubscribes from the hub, so a closed connection never leaves a queue behind.
- **Each browser has a bounded queue** (part of the hub, see 0008). A slow browser misses updates and
  never slows the poller. The next reading carries fresh data.
- **Tests drive the ASGI app directly.** `httpx.ASGITransport` waits for the whole response body, which never
  ends here. The tests play the part of the server instead: they collect what the app sends and decide when
  the client disconnects. They report ASGI `spec_version` 2.3, as uvicorn does, so Starlette listens for the
  disconnect like it does in production.

## Alternatives considered

- **WebSocket**: it is two-way, which we do not need, and it takes more to set up and proxy correctly. SSE is
  plain HTTP, and `EventSource` handles reconnection by itself.
- **Polling an endpoint every few seconds**: simpler, but more requests, and the view always lags behind by up
  to one interval.
- **Long polling**: it fixes the lag but reinvents what SSE already does.
- **Sending only changes, not every reading**: fewer events, but then the browser could not tell "unchanged"
  from "offline", and the snapshot logic would be harder.
- **Testing with a stream that ends after N events**: it would change the production code to suit the test.
  Driving the ASGI app directly tests the real code.

## Consequences

- `EventSource` reconnects on its own after a dropped connection, and the snapshot makes the first event after
  the reconnection correct.
- Browsers limit HTTP/1.1 to about 6 connections per host, and each open stream takes one. HTTP/2 (which the
  production proxy can use) removes the limit.
- The hub lives in memory, so the stream works with a single app process, as in the planned deployment. Several
  workers would each have their own hub and show different data.
- There is no authentication on the stream, like the rest of the API. Access control belongs at the edge
  (Cloudflare Access, planned for M11).
- The tests cover the stream, the headers and the disconnect cleanup. They do not cover a real browser, a real
  proxy or the network between them.

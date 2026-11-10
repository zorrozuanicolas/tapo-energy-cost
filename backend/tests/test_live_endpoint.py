"""Tests of /api/live.

`httpx.ASGITransport` waits for the whole response body, so it cannot read an endless stream. These tests
call the ASGI app directly instead, playing the part of the server: they collect what the app sends and
decide when the client "disconnects".
"""

import asyncio
import json
from collections.abc import Awaitable, Callable, MutableMapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.live import LiveReading
from app.main import create_app
from app.settings import Settings

from .conftest import CONFIG_DIR

TIMEOUT = 2.0  # seconds; only reached when a test is about to fail
T0 = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)

Message = MutableMapping[str, Any]


class Stream:
    """One client connected to /api/live."""

    def __init__(self, app: FastAPI) -> None:
        self.start: Message | None = None
        self._started = asyncio.Event()
        self._chunks: asyncio.Queue[bytes] = asyncio.Queue()
        self._disconnect = asyncio.Event()
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},  # what uvicorn reports
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/live",
            "raw_path": b"/api/live",
            "root_path": "",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", 8000),
        }
        self._task = asyncio.create_task(app(scope, self._receive, self._send))

    async def _receive(self) -> Message:
        await self._disconnect.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            self.start = message
            self._started.set()
        elif message.get("body"):
            await self._chunks.put(message["body"])

    async def headers(self) -> dict[str, str]:
        await asyncio.wait_for(self._started.wait(), TIMEOUT)
        assert self.start is not None
        return {k.decode(): v.decode() for k, v in self.start["headers"]}

    async def next_chunk(self) -> str:
        return (await asyncio.wait_for(self._chunks.get(), TIMEOUT)).decode()

    async def disconnect(self) -> None:
        """The client leaves; wait until the app has finished handling the request."""
        self._disconnect.set()
        await asyncio.wait_for(self._task, TIMEOUT)


def run_live[T](tmp_path: Path, work: Callable[[FastAPI], Awaitable[T]], *, poller_enabled: bool = False) -> T:
    """Start the app (lifespan included) on a database in `tmp_path`, then run `work` with it."""
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'live.db').as_posix()}",
        config_dir=CONFIG_DIR,
        poller_enabled=poller_enabled,
    )

    async def main() -> T:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            return await work(app)

    return asyncio.run(main())


def reading(power_w: float) -> LiveReading:
    return LiveReading(outlet_id=1, power_w=power_w, online=True, ts=T0)


def test_the_stream_has_the_event_stream_headers_and_starts_with_the_snapshot(tmp_path: Path) -> None:
    async def work(app: FastAPI) -> tuple[dict[str, str], str]:
        app.state.ctx.hub.publish(reading(42.5))
        stream = Stream(app)
        try:
            return await stream.headers(), await stream.next_chunk()
        finally:
            await stream.disconnect()

    headers, first = run_live(tmp_path, work)

    assert headers["content-type"].startswith("text/event-stream")
    assert headers["cache-control"] == "no-cache"
    assert headers["x-accel-buffering"] == "no"
    assert first.startswith("data: ")
    assert json.loads(first.removeprefix("data: ")) == {
        "outlet_id": 1,
        "power_w": 42.5,
        "online": True,
        "ts": "2026-11-04T12:00:00Z",
    }


def test_a_reading_published_later_arrives_on_the_open_stream(tmp_path: Path) -> None:
    async def work(app: FastAPI) -> str:
        stream = Stream(app)
        try:
            await stream.headers()
            await asyncio.sleep(0.05)  # let the stream subscribe
            app.state.ctx.hub.publish(reading(7.0))
            return await stream.next_chunk()
        finally:
            await stream.disconnect()

    chunk = run_live(tmp_path, work)

    assert json.loads(chunk.removeprefix("data: "))["power_w"] == 7.0


def test_a_client_that_leaves_is_unsubscribed(tmp_path: Path) -> None:
    async def work(app: FastAPI) -> tuple[int, int]:
        hub = app.state.ctx.hub
        hub.publish(reading(1.0))
        stream = Stream(app)
        await stream.next_chunk()  # the stream is subscribed and running
        while_open = hub.subscriber_count
        await stream.disconnect()
        return while_open, hub.subscriber_count

    assert run_live(tmp_path, work) == (1, 0)


def test_the_stream_carries_the_readings_of_the_real_poller(tmp_path: Path) -> None:
    async def work(app: FastAPI) -> tuple[dict[str, Any], set[int]]:
        stream = Stream(app)
        try:
            event = json.loads((await stream.next_chunk()).removeprefix("data: "))
        finally:
            await stream.disconnect()
        return event, {outlet.id for outlet in app.state.ctx.outlets}

    event, outlet_ids = run_live(tmp_path, work, poller_enabled=True)

    assert event["outlet_id"] in outlet_ids
    assert event["online"] is True
    assert isinstance(event["power_w"], float)

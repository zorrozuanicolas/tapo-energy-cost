"""In-memory hub that passes the latest plug readings from the poller to the connected browsers."""

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime

from .schemas import LiveOut

# How many readings a browser may fall behind before it starts missing updates.
QUEUE_SIZE = 50


@dataclass(frozen=True)
class LiveReading:
    """The state of one plug at one moment."""

    outlet_id: int
    power_w: float | None  # None when the plug could not be read
    online: bool
    ts: datetime  # aware, UTC


class LiveHub:
    """Everything here runs on the one asyncio event loop and never awaits, so no locks are needed."""

    def __init__(self) -> None:
        self._latest: dict[int, LiveReading] = {}
        self._subscribers: set[asyncio.Queue[LiveReading]] = set()

    def publish(self, reading: LiveReading) -> None:
        """Remember the reading and hand it to every subscriber, without ever waiting."""
        self._latest[reading.outlet_id] = reading
        for queue in self._subscribers:
            # A slow browser with a full queue misses this update; the next one carries fresh data.
            # The poller must never wait for a browser.
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(reading)

    def subscribe(self) -> asyncio.Queue[LiveReading]:
        queue: asyncio.Queue[LiveReading] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[LiveReading]) -> None:
        self._subscribers.discard(queue)

    def snapshot(self) -> list[LiveReading]:
        """The latest reading of each plug, by plug id: what a new browser gets first."""
        return [self._latest[outlet_id] for outlet_id in sorted(self._latest)]

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


def _data_frame(reading: LiveReading) -> str:
    return f"data: {LiveOut.from_reading(reading).model_dump_json()}\n\n"


async def live_events(hub: LiveHub, keepalive_seconds: float) -> AsyncGenerator[str, None]:
    """The text of a Server-Sent Events stream: the snapshot, then every new reading.

    When nothing arrives for `keepalive_seconds` it sends a comment line, which browsers ignore but
    which stops proxies from closing an idle connection. Closing the generator (the client left)
    unsubscribes from the hub.
    """
    # Subscribe before taking the snapshot, so a reading published in between is not lost.
    queue = hub.subscribe()
    try:
        for reading in hub.snapshot():
            yield _data_frame(reading)
        while True:
            try:
                reading = await asyncio.wait_for(queue.get(), keepalive_seconds)
            except TimeoutError:
                yield ": keepalive\n\n"
            else:
                yield _data_frame(reading)
    finally:
        hub.unsubscribe(queue)

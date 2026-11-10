import asyncio
import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from app.live import QUEUE_SIZE, LiveHub, LiveReading, live_events

T0 = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def reading(outlet_id: int = 1, power_w: float | None = 10.0, online: bool = True) -> LiveReading:
    return LiveReading(outlet_id=outlet_id, power_w=power_w, online=online, ts=T0)


def test_snapshot_is_empty_before_any_reading() -> None:
    assert LiveHub().snapshot() == []


def test_snapshot_has_the_latest_reading_of_each_plug_by_id() -> None:
    hub = LiveHub()
    hub.publish(reading(outlet_id=2, power_w=20.0))
    hub.publish(reading(outlet_id=1, power_w=10.0))
    hub.publish(reading(outlet_id=2, power_w=25.0))

    assert [(r.outlet_id, r.power_w) for r in hub.snapshot()] == [(1, 10.0), (2, 25.0)]


def test_an_offline_reading_replaces_the_previous_one() -> None:
    hub = LiveHub()
    hub.publish(reading(power_w=10.0))
    hub.publish(reading(power_w=None, online=False))

    [latest] = hub.snapshot()
    assert latest.online is False
    assert latest.power_w is None


def test_every_subscriber_receives_each_reading() -> None:
    async def work() -> tuple[list[LiveReading], list[LiveReading]]:
        hub = LiveHub()
        first, second = hub.subscribe(), hub.subscribe()
        hub.publish(reading(power_w=1.0))
        hub.publish(reading(power_w=2.0))
        return (
            [first.get_nowait(), first.get_nowait()],
            [second.get_nowait(), second.get_nowait()],
        )

    got_first, got_second = asyncio.run(work())

    assert [r.power_w for r in got_first] == [1.0, 2.0]
    assert got_first == got_second


def test_an_unsubscribed_queue_gets_nothing_more() -> None:
    async def work() -> int:
        hub = LiveHub()
        queue = hub.subscribe()
        hub.unsubscribe(queue)
        hub.publish(reading())
        return queue.qsize()

    assert asyncio.run(work()) == 0


def test_unsubscribing_twice_is_harmless() -> None:
    async def work() -> None:
        hub = LiveHub()
        queue = hub.subscribe()
        hub.unsubscribe(queue)
        hub.unsubscribe(queue)

    asyncio.run(work())


def test_a_full_queue_does_not_block_or_break_the_others() -> None:
    async def work() -> tuple[int, int, float | None]:
        hub = LiveHub()
        slow, fast = hub.subscribe(), hub.subscribe()
        for i in range(QUEUE_SIZE):
            hub.publish(reading(power_w=float(i)))
        for _ in range(QUEUE_SIZE):
            fast.get_nowait()  # the fast browser keeps up, the slow one never reads

        hub.publish(reading(power_w=999.0))  # `slow` is full: it misses this one

        return slow.qsize(), fast.qsize(), fast.get_nowait().power_w

    slow_size, fast_size, fast_power = asyncio.run(work())

    assert slow_size == QUEUE_SIZE
    assert fast_size == 1
    assert fast_power == 999.0


def test_a_reading_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        reading().power_w = 5.0  # type: ignore[misc]


def frame(outlet_id: int, power_w: float | None, online: bool = True) -> str:
    event = {"outlet_id": outlet_id, "power_w": power_w, "online": online, "ts": "2026-11-04T12:00:00Z"}
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


def test_the_stream_starts_with_the_snapshot_in_plug_order() -> None:
    async def work() -> list[str]:
        hub = LiveHub()
        hub.publish(reading(outlet_id=2, power_w=20.0))
        hub.publish(reading(outlet_id=1, power_w=10.0))
        events = live_events(hub, keepalive_seconds=60)
        try:
            return [await anext(events), await anext(events)]
        finally:
            await events.aclose()

    assert asyncio.run(work()) == [frame(1, 10.0), frame(2, 20.0)]


def test_a_new_reading_arrives_as_a_frame() -> None:
    async def work() -> str:
        hub = LiveHub()
        events = live_events(hub, keepalive_seconds=60)
        pending = asyncio.ensure_future(anext(events))
        await asyncio.sleep(0)  # let the stream subscribe and wait
        hub.publish(reading(outlet_id=1, power_w=5.5))
        try:
            return await asyncio.wait_for(pending, timeout=1)
        finally:
            await events.aclose()

    assert asyncio.run(work()) == frame(1, 5.5)


def test_an_offline_reading_has_a_null_power() -> None:
    async def work() -> str:
        hub = LiveHub()
        hub.publish(reading(power_w=None, online=False))
        events = live_events(hub, keepalive_seconds=60)
        try:
            return await anext(events)
        finally:
            await events.aclose()

    assert asyncio.run(work()) == frame(1, None, online=False)


def test_readings_published_while_the_client_is_slow_are_delivered_in_order() -> None:
    async def work() -> list[str]:
        hub = LiveHub()
        events = live_events(hub, keepalive_seconds=60)
        first = asyncio.ensure_future(anext(events))
        await asyncio.sleep(0)
        for watts in (1.0, 2.0, 3.0):  # all published before the client reads any
            hub.publish(reading(power_w=watts))
        try:
            return [await first, await anext(events), await anext(events)]
        finally:
            await events.aclose()

    assert asyncio.run(work()) == [frame(1, 1.0), frame(1, 2.0), frame(1, 3.0)]


def test_a_keepalive_is_sent_when_nothing_arrives() -> None:
    async def work() -> str:
        events = live_events(LiveHub(), keepalive_seconds=0.01)
        try:
            return await asyncio.wait_for(anext(events), timeout=1)
        finally:
            await events.aclose()

    assert asyncio.run(work()) == ": keepalive\n\n"


def test_closing_the_stream_unsubscribes() -> None:
    async def work() -> tuple[int, int]:
        hub = LiveHub()
        events = live_events(hub, keepalive_seconds=0.01)
        await anext(events)  # the first keepalive: the stream is subscribed and waiting
        while_open = hub.subscriber_count
        await events.aclose()
        return while_open, hub.subscriber_count

    assert asyncio.run(work()) == (1, 0)

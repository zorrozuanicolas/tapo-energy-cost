import asyncio
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from app.live import QUEUE_SIZE, LiveHub, LiveReading

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

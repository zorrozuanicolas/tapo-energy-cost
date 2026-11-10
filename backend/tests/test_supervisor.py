import asyncio
import logging

import pytest

from app.supervisor import supervise


async def run_for(seconds: float, task: asyncio.Task[None]) -> None:
    await asyncio.sleep(seconds)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_a_crashing_task_is_logged_and_restarted(caplog: pytest.LogCaptureFixture) -> None:
    calls = 0

    async def crashing() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    async def main() -> None:
        await run_for(0.05, asyncio.create_task(supervise("worker", crashing, restart_delay=0.001)))

    asyncio.run(main())

    assert calls >= 3
    assert "Task 'worker' crashed" in caplog.text
    assert "boom" in caplog.text  # the traceback is logged


def test_a_task_that_returns_is_restarted(caplog: pytest.LogCaptureFixture) -> None:
    calls = 0

    async def returning() -> None:
        nonlocal calls
        calls += 1

    async def main() -> None:
        await run_for(0.05, asyncio.create_task(supervise("worker", returning, restart_delay=0.001)))

    caplog.set_level(logging.WARNING, logger="tapo.supervisor")
    asyncio.run(main())

    assert calls >= 3
    assert "ended unexpectedly" in caplog.text


def test_cancelling_the_supervisor_cancels_the_task() -> None:
    state = {"running": False, "cancelled": False}

    async def forever() -> None:
        state["running"] = True
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    async def main() -> None:
        await run_for(0.02, asyncio.create_task(supervise("worker", forever)))

    asyncio.run(main())

    assert state == {"running": True, "cancelled": True}

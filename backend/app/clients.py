"""Clients that read the power of one plug: a real Tapo plug, or a fake one for development."""

import asyncio
import math
import random
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from .outlets import OutletInfo
from .settings import Settings


class OutletClient(Protocol):
    """What the poller needs from a plug."""

    async def read_power_w(self) -> float:
        """Current power in watts. Raises if the plug cannot be read."""
        ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


class MockOutletClient:
    """Fake readings, so the whole app can run without plugs."""

    def __init__(
        self,
        index: int,
        tz: ZoneInfo,
        clock: Callable[[], datetime] = _utc_now,
        rng: random.Random | None = None,
    ) -> None:
        self._index = index
        self._tz = tz
        self._clock = clock  # tests pass a fixed clock
        self._rng = rng or random.Random()

    async def read_power_w(self) -> float:
        now = self._clock()
        if self._index == 0:
            # A fridge: the compressor cycles on and off, with a small standby draw.
            seconds = now.timestamp()
            running = math.sin(seconds / 900.0) > -0.2
            return round(2.0 + (55.0 + 20.0 * math.sin(seconds / 37.0) if running else 0.0), 1)
        # A desk: busy during office hours, nearly idle otherwise.
        local = now.astimezone(self._tz)
        working = local.weekday() < 5 and 9 <= local.hour < 19
        noise = self._rng.random()
        return round(110.0 + 40.0 * noise if working else 3.0 + 2.0 * noise, 1)


class TapoOutletClient:
    """Reads one real P110/P115 through the `tapo` library."""

    def __init__(self, outlet: OutletInfo, username: str, password: str, api_client: Any = None) -> None:
        if api_client is None:
            # Imported here so mock mode, and the tests, never load the library.
            from tapo import ApiClient

            api_client = ApiClient(username, password)
        self._outlet = outlet
        self._api = api_client
        # The logged-in connection to the plug; None until the first read, and again after an error.
        self._handler: Any = None
        # A plug rejects two logins at once, so only one read runs at a time.
        self._lock = asyncio.Lock()

    async def _connect(self) -> Any:
        if self._handler is None:
            connect = self._api.p115 if self._outlet.model == "p115" else self._api.p110
            self._handler = await connect(self._outlet.ip)
        return self._handler

    async def read_power_w(self) -> float:
        async with self._lock:
            try:
                handler = await self._connect()
                usage = await handler.get_energy_usage()
                if usage.current_power is not None:
                    return float(usage.current_power) / 1000.0  # this call reports milliwatts
                return float((await handler.get_current_power()).current_power)  # this one, watts
            except Exception:
                self._handler = None  # log in again on the next read
                raise


def make_client(outlet: OutletInfo, index: int, settings: Settings, tz: ZoneInfo) -> OutletClient:
    """The mock client or the real one, according to `settings.tapo_mock`."""
    if settings.tapo_mock:
        return MockOutletClient(index, tz)
    return TapoOutletClient(outlet, settings.tapo_username, settings.tapo_password.get_secret_value())

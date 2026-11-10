import asyncio
import random
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.clients import MockOutletClient, TapoOutletClient, make_client
from app.outlets import OutletInfo
from app.settings import Settings

TZ = ZoneInfo("America/Montevideo")


def at(year: int, month: int, day: int, hour: int = 0) -> datetime:
    """A local (Montevideo) time, so the tests read like the plug owner's clock."""
    return datetime(year, month, day, hour, tzinfo=TZ)


def mock(index: int, now: datetime) -> MockOutletClient:
    return MockOutletClient(index, TZ, clock=lambda: now, rng=random.Random(1))


def outlet(model: str = "p110") -> OutletInfo:
    return OutletInfo(id=1, slug="fridge", name="Fridge", ip="192.168.0.10", model=model)


# --- mock ------------------------------------------------------------------------------------------


def test_mock_is_repeatable_with_a_fixed_clock_and_seed() -> None:
    now = at(2026, 11, 4, 12)

    first = asyncio.run(mock(1, now).read_power_w())
    second = asyncio.run(mock(1, now).read_power_w())

    assert first == second


def test_mock_fridge_stays_in_its_range() -> None:
    start = at(2026, 11, 4).timestamp()
    readings = [
        asyncio.run(mock(0, datetime.fromtimestamp(start + step * 60, UTC)).read_power_w())
        for step in range(24 * 60)  # one day, a reading per minute
    ]

    assert all(2.0 <= watts <= 77.0 for watts in readings)
    assert min(readings) == 2.0  # standby while the compressor is off
    assert max(readings) > 40.0  # running


def test_mock_desk_is_busy_in_office_hours() -> None:
    watts = asyncio.run(mock(1, at(2026, 11, 4, 10)).read_power_w())  # Wednesday, 10:00

    assert 110.0 <= watts <= 150.0


@pytest.mark.parametrize(
    "when",
    [at(2026, 11, 4, 22), at(2026, 11, 4, 8), at(2026, 11, 7, 11)],  # evening, early morning, Saturday
)
def test_mock_desk_is_idle_outside_office_hours(when: datetime) -> None:
    watts = asyncio.run(mock(1, when).read_power_w())

    assert 3.0 <= watts <= 5.0


# --- Tapo ------------------------------------------------------------------------------------------


class FakeHandler:
    """Stands in for the `tapo` handler of a plug."""

    def __init__(self, milliwatts: int | None = 12_500, watts: int = 7, delay: float = 0.0) -> None:
        self.milliwatts = milliwatts
        self.watts = watts
        self.delay = delay
        self.fail = False
        self.running = 0
        self.max_running = 0

    async def get_energy_usage(self) -> Any:
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        try:
            await asyncio.sleep(self.delay)
            if self.fail:
                raise ConnectionError("plug unreachable")
            return SimpleNamespace(current_power=self.milliwatts)
        finally:
            self.running -= 1

    async def get_current_power(self) -> Any:
        return SimpleNamespace(current_power=self.watts)


class FakeApi:
    """Stands in for `tapo.ApiClient`; counts the logins."""

    def __init__(self, handler: FakeHandler) -> None:
        self.handler = handler
        self.logins: list[tuple[str, str]] = []  # (model, ip)

    async def p110(self, ip: str) -> FakeHandler:
        self.logins.append(("p110", ip))
        return self.handler

    async def p115(self, ip: str) -> FakeHandler:
        self.logins.append(("p115", ip))
        return self.handler


def tapo(api: FakeApi, model: str = "p110") -> TapoOutletClient:
    return TapoOutletClient(outlet(model), "user", "pass", api_client=api)


def test_tapo_converts_milliwatts_to_watts() -> None:
    client = tapo(FakeApi(FakeHandler(milliwatts=12_500)))

    assert asyncio.run(client.read_power_w()) == 12.5


def test_tapo_falls_back_to_current_power_when_usage_has_none() -> None:
    client = tapo(FakeApi(FakeHandler(milliwatts=None, watts=7)))

    assert asyncio.run(client.read_power_w()) == 7.0


def test_tapo_logs_in_once_and_reuses_the_connection() -> None:
    api = FakeApi(FakeHandler())
    client = tapo(api)

    async def work() -> None:
        await client.read_power_w()
        await client.read_power_w()

    asyncio.run(work())

    assert api.logins == [("p110", "192.168.0.10")]


def test_tapo_logs_in_again_after_an_error() -> None:
    handler = FakeHandler()
    api = FakeApi(handler)
    client = tapo(api)

    async def work() -> None:
        handler.fail = True
        with pytest.raises(ConnectionError):
            await client.read_power_w()
        handler.fail = False
        await client.read_power_w()

    asyncio.run(work())

    assert len(api.logins) == 2


def test_tapo_uses_the_p115_connector_for_p115_plugs() -> None:
    api = FakeApi(FakeHandler())

    asyncio.run(tapo(api, model="p115").read_power_w())

    assert api.logins == [("p115", "192.168.0.10")]


def test_tapo_never_reads_the_same_plug_twice_at_once() -> None:
    handler = FakeHandler(delay=0.01)
    client = tapo(FakeApi(handler))

    async def work() -> None:
        await asyncio.gather(*(client.read_power_w() for _ in range(5)))

    asyncio.run(work())

    assert handler.max_running == 1


# --- make_client -----------------------------------------------------------------------------------


def test_make_client_returns_the_mock_by_default() -> None:
    client = make_client(outlet(), 0, Settings(_env_file=None), TZ)

    assert isinstance(client, MockOutletClient)


def test_make_client_returns_the_real_client_when_mock_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAPO_MOCK", "false")
    monkeypatch.setenv("TAPO_USERNAME", "me@example.com")
    monkeypatch.setenv("TAPO_PASSWORD", "secret")

    client = make_client(outlet(), 0, Settings(_env_file=None), TZ)

    assert isinstance(client, TapoOutletClient)

"""Background task that reads every plug on a fixed interval and records the energy used."""

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .clients import OutletClient
from .db import utcnow
from .energy import record_sample
from .live import LiveHub, LiveReading
from .outlets import OutletInfo
from .settings import Settings

log = logging.getLogger("tapo.poller")

# Longest a single read may take. It is also capped by the polling interval, so one stuck plug
# cannot make a round overlap the next one.
MAX_READ_TIMEOUT_SECONDS = 20.0


class Poller:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        hub: LiveHub,
        clients: dict[int, OutletClient],
        outlets: list[OutletInfo],
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._hub = hub
        self._clients = clients  # by outlet id
        self._outlets = outlets
        self._clock = clock  # tests pass a controllable clock
        self._read_timeout = min(MAX_READ_TIMEOUT_SECONDS, float(settings.poll_interval_seconds))
        # The last good sample of each plug. A plug that fails loses its entry, so no energy is
        # added across an outage.
        self._prev: dict[int, tuple[datetime, float]] = {}
        self._failures: defaultdict[int, int] = defaultdict(int)

    async def run(self, interval: float | None = None) -> None:
        """Poll forever, once per interval (the setting by default). Stops only when cancelled."""
        interval = float(self._settings.poll_interval_seconds) if interval is None else interval
        log.info("Polling %d outlet(s) every %gs", len(self._outlets), interval)
        while True:
            started = time.monotonic()
            await self.poll_once()
            await asyncio.sleep(max(0.0, interval - (time.monotonic() - started)))

    async def poll_once(self) -> None:
        """One round: read every plug at the same time, so a slow plug does not delay the others."""
        await asyncio.gather(*(self._sample(outlet) for outlet in self._outlets))

    async def _sample(self, outlet: OutletInfo) -> None:
        """Handle one plug. Never raises (except when cancelled): one plug must not stop the rest."""
        try:
            power_w = await asyncio.wait_for(self._clients[outlet.id].read_power_w(), self._read_timeout)
        except Exception as exc:  # noqa: BLE001 - any failure just means "offline this round"
            self._plug_failed(outlet, exc)
            return

        if self._failures[outlet.id]:
            log.info("Outlet '%s' is back online", outlet.slug)
            self._failures[outlet.id] = 0

        ts = self._clock()
        try:
            async with self._session_factory() as session:
                await record_sample(
                    session, outlet.id, ts, power_w, self._prev.get(outlet.id), self._settings.max_gap_seconds
                )
                # The reading and its energy are saved together or not at all.
                await session.commit()
        except Exception:
            log.exception("Could not store the reading of outlet '%s'", outlet.slug)
            self._prev.pop(outlet.id, None)  # the energy of this interval is lost: do not bridge it
        else:
            self._prev[outlet.id] = (ts, power_w)
        # The reading is real even if saving it failed, so the live view still shows it.
        self._hub.publish(LiveReading(outlet_id=outlet.id, power_w=power_w, online=True, ts=ts))

    def _plug_failed(self, outlet: OutletInfo, exc: Exception) -> None:
        self._failures[outlet.id] += 1
        count = self._failures[outlet.id]
        # Log the first failure and then one in twenty, so a long outage does not flood the log.
        if count == 1 or count % 20 == 0:
            log.warning("Outlet '%s' unreachable (%d in a row): %r", outlet.slug, count, exc)
        self._prev.pop(outlet.id, None)  # do not integrate energy across an outage
        self._hub.publish(LiveReading(outlet_id=outlet.id, power_w=None, online=False, ts=self._clock()))

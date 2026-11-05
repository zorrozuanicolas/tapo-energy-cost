"""The FastAPI application.

Run it with `uvicorn app.main:create_app --factory`. There is no module-level `app`, so importing
this module reads no settings and touches no files.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Annotated, cast
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .aggregation import Granularity, RangeError, consumption
from .billing import BANDS, BillingConfig, load_billing_config
from .db import HourlyEnergy, make_engine, make_session_factory
from .migrate import upgrade_database_async
from .outlets import OutletInfo, load_outlets, sync_outlets
from .schemas import ConsumptionResponse, HealthOut, OutletOut, RangeOut, TariffOut
from .settings import Settings


@dataclass(frozen=True)
class AppState:
    """Everything the endpoints need, built once at startup."""

    settings: Settings
    tz: ZoneInfo
    billing: BillingConfig
    outlets: list[OutletInfo]
    session_factory: async_sessionmaker[AsyncSession]


def get_state(request: Request) -> AppState:
    """Dependency: the state built at startup. Tests can override it."""
    return cast(AppState, request.app.state.ctx)


StateDep = Annotated[AppState, Depends(get_state)]


async def get_session(state: StateDep) -> AsyncIterator[AsyncSession]:
    """Dependency: one database session per request."""
    async with state.session_factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_now() -> datetime:
    """Dependency: the current time, aware and in UTC. Tests override it to fix the clock."""
    return datetime.now(UTC)


NowDep = Annotated[datetime, Depends(get_now)]


def _outlets_out(state: AppState) -> list[OutletOut]:
    return [OutletOut(id=o.id, slug=o.slug, name=o.name) for o in state.outlets]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Read the files first: a broken config should stop the app before it touches the database.
        billing = load_billing_config(settings.config_dir)
        configs = load_outlets(settings.config_dir)

        await upgrade_database_async(settings.database_url)
        engine = make_engine(settings.database_url)
        try:
            session_factory = make_session_factory(engine)
            outlets = await sync_outlets(session_factory, configs)
            app.state.ctx = AppState(
                settings=settings,
                tz=ZoneInfo(settings.timezone),
                billing=billing,
                outlets=outlets,
                session_factory=session_factory,
            )
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Tapo energy cost", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET"])

    @app.get("/api/health")
    async def health(state: StateDep) -> HealthOut:
        return HealthOut(outlets=_outlets_out(state))

    @app.get("/api/outlets")
    async def list_outlets(state: StateDep) -> list[OutletOut]:
        return _outlets_out(state)

    @app.get("/api/range")
    async def data_range(state: StateDep, session: SessionDep) -> RangeOut:
        """The first local day with data, so the history navigator knows how far back it can go."""
        first = (await session.execute(select(func.min(HourlyEnergy.hour_start)))).scalar_one()
        return RangeOut(earliest=None if first is None else first.astimezone(state.tz).date())

    @app.get("/api/consumption")
    async def get_consumption(
        state: StateDep,
        session: SessionDep,
        now: NowDep,
        granularity: Granularity,
        from_: Annotated[date, Query(alias="from")],
        to: date,
    ) -> ConsumptionResponse:
        """kWh and cost (VAT included) per outlet, grouped by hour, day or month.

        `from` is inclusive and `to` exclusive, as local dates. For `month`, both snap to whole months.
        """
        try:
            return await consumption(session, state.billing, state.tz, state.outlets, granularity, from_, to, now)
        except RangeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/tariff")
    async def get_tariff(
        state: StateDep, now: NowDep, day: Annotated[date | None, Query(alias="date")] = None
    ) -> TariffOut:
        """The tariff in force on a local date (today by default)."""
        day = day or now.astimezone(state.tz).date()
        tariff = state.billing.tariff_for(day)
        if tariff is None:
            raise HTTPException(status_code=404, detail=f"No tariff configured for {day}")
        return TariffOut(
            valid_from=tariff.valid_from,
            vat=tariff.vat,
            peak_start=tariff.peak_start,
            peak_end=tariff.peak_end,
            rates={band: tariff.rate(band) for band in BANDS},
            rates_with_vat={band: round(tariff.rate_with_vat(band), 4) for band in BANDS},
        )

    return app

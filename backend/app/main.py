"""The FastAPI application.

Run it with `uvicorn app.main:create_app --factory`. There is no module-level `app`, so importing
this module reads no settings and touches no files.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, cast
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .billing import BillingConfig, load_billing_config
from .db import make_engine, make_session_factory
from .migrate import upgrade_database_async
from .outlets import OutletInfo, load_outlets, sync_outlets
from .schemas import HealthOut, OutletOut
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
        return HealthOut(outlets=[OutletOut(id=o.id, slug=o.slug, name=o.name) for o in state.outlets])

    return app

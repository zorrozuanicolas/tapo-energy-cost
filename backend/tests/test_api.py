import asyncio
import sqlite3
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from app.main import create_app
from app.outlets import load_outlets
from app.settings import Settings

from .conftest import CONFIG_DIR

ORIGIN = "http://localhost:5173"


def run_app[T](tmp_path: Path, work: Callable[[httpx.AsyncClient], Awaitable[T]], **overrides: object) -> T:
    """Start the app (its lifespan included) on a database in `tmp_path`, then run `work` with a client."""
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'api.db').as_posix()}",
        config_dir=CONFIG_DIR,
        **overrides,  # type: ignore[arg-type]
    )

    async def main() -> T:
        app = create_app(settings)
        # ASGITransport does not run the lifespan, so enter it here.
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await work(client)

    return asyncio.run(main())


def test_health_lists_the_configured_outlets(tmp_path: Path) -> None:
    async def work(client: httpx.AsyncClient) -> httpx.Response:
        return await client.get("/api/health")

    response = run_app(tmp_path, work)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert [o["slug"] for o in body["outlets"]] == [o.slug for o in load_outlets(CONFIG_DIR)]


def test_startup_creates_the_tables_in_an_empty_database(tmp_path: Path) -> None:
    async def work(client: httpx.AsyncClient) -> None:
        return None

    run_app(tmp_path, work)

    with sqlite3.connect(tmp_path / "api.db") as connection:
        names = {n for (n,) in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"outlets", "readings", "hourly_energy"} <= names


def test_restarting_keeps_the_same_outlet_ids(tmp_path: Path) -> None:
    async def work(client: httpx.AsyncClient) -> list[tuple[int, str]]:
        body = (await client.get("/api/health")).json()
        return [(o["id"], o["slug"]) for o in body["outlets"]]

    assert run_app(tmp_path, work) == run_app(tmp_path, work)


def test_allowed_origin_gets_the_cors_header(tmp_path: Path) -> None:
    async def work(client: httpx.AsyncClient) -> httpx.Response:
        return await client.get("/api/health", headers={"Origin": ORIGIN})

    response = run_app(tmp_path, work)
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_other_origins_do_not_get_the_cors_header(tmp_path: Path) -> None:
    async def work(client: httpx.AsyncClient) -> httpx.Response:
        return await client.get("/api/health", headers={"Origin": "http://evil.example"})

    response = run_app(tmp_path, work)
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers

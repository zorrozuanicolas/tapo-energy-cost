import asyncio
import shutil
import sqlite3
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.billing import BANDS, load_billing_config
from app.db import HourlyEnergy
from app.main import create_app, get_now
from app.outlets import load_outlets
from app.settings import Settings

from .conftest import CONFIG_DIR

ORIGIN = "http://localhost:5173"


def run_app[T](
    tmp_path: Path,
    work: Callable[[httpx.AsyncClient], Awaitable[T]],
    *,
    now: datetime | None = None,
    hours: Sequence[datetime] = (),
    config_dir: Path = CONFIG_DIR,
) -> T:
    """Start the app (its lifespan included) on a database in `tmp_path`, then run `work` with a client.

    `now` fixes the app's clock. `hours` are UTC hours that get 1 kWh of data for the first outlet.
    """
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'api.db').as_posix()}",
        config_dir=config_dir,
        poller_enabled=False,  # these tests are about the API; test_app_poller.py covers the poller
    )

    async def main() -> T:
        app = create_app(settings)
        if now is not None:
            app.dependency_overrides[get_now] = lambda: now
        # ASGITransport does not run the lifespan, so enter it here.
        async with app.router.lifespan_context(app):
            async with app.state.ctx.session_factory() as session:
                session.add_all(
                    HourlyEnergy(outlet_id=1, hour_start=h, kwh=1.0, seconds_covered=3600) for h in hours
                )
                await session.commit()
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


def test_outlets_are_listed_in_config_order(tmp_path: Path) -> None:
    async def work(client: httpx.AsyncClient) -> httpx.Response:
        return await client.get("/api/outlets")

    response = run_app(tmp_path, work)

    assert response.status_code == 200
    expected = load_outlets(CONFIG_DIR)
    assert [(o["slug"], o["name"]) for o in response.json()] == [(o.slug, o.name) for o in expected]


def test_range_is_null_on_an_empty_database(tmp_path: Path) -> None:
    async def work(client: httpx.AsyncClient) -> httpx.Response:
        return await client.get("/api/range")

    response = run_app(tmp_path, work)
    assert response.json() == {"earliest": None}


def test_range_is_the_local_date_of_the_earliest_hour(tmp_path: Path) -> None:
    # 01:00 UTC on 1 March is 22:00 on 28 February in Montevideo (UTC-3).
    hours = [datetime(2026, 3, 1, 1, tzinfo=UTC), datetime(2026, 3, 5, 12, tzinfo=UTC)]

    async def work(client: httpx.AsyncClient) -> httpx.Response:
        return await client.get("/api/range")

    response = run_app(tmp_path, work, hours=hours)
    assert response.json() == {"earliest": "2026-02-28"}


def test_tariff_for_a_date_matches_the_configuration(tmp_path: Path) -> None:
    day = date(2026, 6, 15)
    tariff = load_billing_config(CONFIG_DIR).tariff_for(day)
    assert tariff is not None

    async def work(client: httpx.AsyncClient) -> httpx.Response:
        return await client.get("/api/tariff", params={"date": day.isoformat()})

    body = run_app(tmp_path, work).json()

    assert body["valid_from"] == tariff.valid_from.isoformat()
    assert (body["vat"], body["peak_start"], body["peak_end"]) == (tariff.vat, tariff.peak_start, tariff.peak_end)
    assert body["rates"] == {band: tariff.rate(band) for band in BANDS}
    assert body["rates_with_vat"] == {
        band: pytest.approx(tariff.rate(band) * tariff.vat, abs=1e-4) for band in BANDS
    }


def test_tariff_defaults_to_today_in_local_time(tmp_path: Path) -> None:
    # A copy of the configuration with a second tariff that starts on 1 January 2027.
    config_dir = tmp_path / "config"
    shutil.copytree(CONFIG_DIR, config_dir)
    with (config_dir / "tariffs.yaml").open("a", encoding="utf-8") as file:
        file.write(
            "  - valid_from: 2027-01-01\n    vat: 1.22\n    peak_window: {start: 17, end: 21}\n"
            "    rates: {punta: 13.0, llano: 6.0, valle: 3.0}\n"
        )

    # 01:00 UTC on 1 January 2027 is still 31 December 2026 in Montevideo, so the old tariff applies.
    now = datetime(2027, 1, 1, 1, tzinfo=UTC)

    async def work(client: httpx.AsyncClient) -> httpx.Response:
        return await client.get("/api/tariff")

    body = run_app(tmp_path, work, now=now, config_dir=config_dir).json()
    assert body["valid_from"] == "2026-01-01"


def test_tariff_before_the_first_one_is_not_found(tmp_path: Path) -> None:
    first = load_billing_config(CONFIG_DIR).tariffs[0].valid_from
    before = first - timedelta(days=1)

    async def work(client: httpx.AsyncClient) -> httpx.Response:
        return await client.get("/api/tariff", params={"date": before.isoformat()})

    response = run_app(tmp_path, work)
    assert response.status_code == 404
    assert before.isoformat() in response.json()["detail"]


def test_tariff_with_a_malformed_date_is_rejected(tmp_path: Path) -> None:
    async def work(client: httpx.AsyncClient) -> httpx.Response:
        return await client.get("/api/tariff", params={"date": "yesterday"})

    assert run_app(tmp_path, work).status_code == 422


# 2026-06-15 is a Monday and not a holiday. In Montevideo (UTC-3), 06:00 UTC is 03:00 (valle)
# and 21:00 UTC is 18:00 (punta).
JUNE_15_HOURS = [datetime(2026, 6, 15, 6, tzinfo=UTC), datetime(2026, 6, 15, 21, tzinfo=UTC)]


def get_consumption(tmp_path: Path, params: dict[str, str], **kwargs: Any) -> httpx.Response:
    async def work(client: httpx.AsyncClient) -> httpx.Response:
        return await client.get("/api/consumption", params=params)

    return run_app(tmp_path, work, **kwargs)


def test_consumption_prices_the_stored_hours(tmp_path: Path) -> None:
    tariff = load_billing_config(CONFIG_DIR).tariff_for(date(2026, 6, 15))
    assert tariff is not None
    expected_cost = tariff.rate_with_vat("valle") + tariff.rate_with_vat("punta")

    response = get_consumption(
        tmp_path,
        {"granularity": "day", "from": "2026-06-15", "to": "2026-06-16"},
        hours=JUNE_15_HOURS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["granularity"] == "day"
    assert body["timezone"] == "America/Montevideo"
    assert len(body["buckets"]) == 1
    day_value = body["buckets"][0]["outlets"]["1"]  # the seeded hours belong to outlet 1
    assert day_value["kwh"] == pytest.approx(2)
    assert day_value["cost"] == pytest.approx(expected_cost, abs=1e-3)
    assert body["totals"]["1"] == day_value
    assert body["totals"]["2"] == {"kwh": 0, "cost": 0}
    assert body["warnings"] == []


def test_consumption_json_has_string_outlet_keys_and_local_offsets(tmp_path: Path) -> None:
    body = get_consumption(
        tmp_path, {"granularity": "day", "from": "2026-06-15", "to": "2026-06-16"}, hours=JUNE_15_HOURS
    ).json()

    slugs = [o["slug"] for o in body["outlets"]]
    assert slugs == [o.slug for o in load_outlets(CONFIG_DIR)]
    assert set(body["totals"]) == {str(o["id"]) for o in body["outlets"]}
    bucket = body["buckets"][0]
    assert set(bucket["outlets"]) == set(body["totals"])
    assert bucket["start"] == "2026-06-15T00:00:00-03:00"
    assert bucket["end"] == "2026-06-16T00:00:00-03:00"


def test_consumption_marks_the_bucket_that_contains_now(tmp_path: Path) -> None:
    now = datetime(2026, 6, 15, 12, tzinfo=UTC)
    body = get_consumption(
        tmp_path, {"granularity": "day", "from": "2026-06-14", "to": "2026-06-17"}, now=now
    ).json()
    assert [b["partial"] for b in body["buckets"]] == [False, True, False]


def test_consumption_reports_missing_holidays_as_a_warning(tmp_path: Path) -> None:
    body = get_consumption(tmp_path, {"granularity": "day", "from": "2027-01-04", "to": "2027-01-05"}).json()
    assert body["warnings"] == [{"code": "missing_holidays", "year": 2027}]


def test_consumption_with_an_invalid_range_is_a_400(tmp_path: Path) -> None:
    same_day = get_consumption(tmp_path, {"granularity": "day", "from": "2026-06-15", "to": "2026-06-15"})
    too_long = get_consumption(tmp_path, {"granularity": "hour", "from": "2026-06-01", "to": "2026-06-20"})

    assert same_day.status_code == 400
    assert "earlier" in same_day.json()["detail"]
    assert too_long.status_code == 400
    assert "hour granularity" in too_long.json()["detail"]


@pytest.mark.parametrize(
    "params",
    [
        {"granularity": "week", "from": "2026-06-15", "to": "2026-06-16"},
        {"granularity": "day", "from": "2026-06-15"},
        {"granularity": "day", "from": "yesterday", "to": "2026-06-16"},
    ],
    ids=["unknown-granularity", "missing-to", "malformed-date"],
)
def test_consumption_with_bad_parameters_is_a_422(tmp_path: Path, params: dict[str, str]) -> None:
    assert get_consumption(tmp_path, params).status_code == 422

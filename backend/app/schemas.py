"""Response models of the REST API. They are the contract the frontend relies on."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .billing import Band


class _Schema(BaseModel):
    """Base for every response model: immutable, and unknown fields are an error."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class OutletOut(_Schema):
    id: int
    slug: str
    name: str


class HealthOut(_Schema):
    status: Literal["ok"] = "ok"
    outlets: list[OutletOut]


class OutletValue(_Schema):
    kwh: float
    cost: float  # pesos, VAT included


class BucketOut(_Schema):
    start: datetime  # local time, timezone-aware
    end: datetime
    has_data: bool
    partial: bool  # the hour, day or month is still in progress
    band: Band | None = None  # hour granularity only
    rate_per_kwh: float | None = None  # hour granularity only, VAT included
    outlets: dict[int, OutletValue]


class MissingHolidaysWarning(_Schema):
    """The holiday list has no entry for `year`, so holidays are priced as business days."""

    code: Literal["missing_holidays"] = "missing_holidays"
    year: int


class NoTariffWarning(_Schema):
    """Some hours are before the first tariff, so they have no cost."""

    code: Literal["no_tariff"] = "no_tariff"
    since: date  # first affected local day


# `code` tells the two apart, so a warning can never mix their fields.
Warning_ = Annotated[MissingHolidaysWarning | NoTariffWarning, Field(discriminator="code")]


class ConsumptionResponse(_Schema):
    granularity: Literal["hour", "day", "month"]
    timezone: str
    outlets: list[OutletOut]
    buckets: list[BucketOut]
    totals: dict[int, OutletValue]
    warnings: list[Warning_]


class TariffOut(_Schema):
    valid_from: date
    vat: float
    peak_start: int
    peak_end: int
    rates: dict[Band, float]  # without VAT
    rates_with_vat: dict[Band, float]


class RangeOut(_Schema):
    earliest: date | None  # first local day with any data, None if the database is empty

"""UTE triple-hour tariff: versioned tariffs, holidays and the Valle/Llano/Punta band of an hour."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, get_args

Band = Literal["valle", "llano", "punta"]
BANDS: tuple[Band, ...] = get_args(Band)

# Valle is always 00:00 - 07:00 (UTE Plan Inteligente Hogares, triple horario).
VALLE_END_HOUR = 7


@dataclass(frozen=True)
class Tariff:
    """One set of prices. It applies from `valid_from` until the next tariff starts."""

    valid_from: date
    vat: float
    peak_start: int
    peak_end: int
    rates: dict[Band, float]  # $/kWh without VAT

    def rate(self, band: Band) -> float:
        return self.rates[band]

    def rate_with_vat(self, band: Band) -> float:
        return self.rates[band] * self.vat


@dataclass
class BillingConfig:
    tariffs: list[Tariff]  # sorted by valid_from
    holidays: dict[int, dict[date, str]]  # year -> {date: name}

    def tariff_for(self, day: date) -> Tariff | None:
        """The tariff in force on `day`, or None if `day` is before the first tariff."""
        current: Tariff | None = None
        for tariff in self.tariffs:
            if tariff.valid_from <= day:
                current = tariff
            else:
                break
        return current

    def has_holidays_for(self, year: int) -> bool:
        return year in self.holidays

    def is_holiday(self, day: date) -> bool:
        return day in self.holidays.get(day.year, {})

    def is_business_day(self, day: date) -> bool:
        return day.weekday() < 5 and not self.is_holiday(day)

    def band_for(self, local: datetime, tariff: Tariff) -> Band:
        """Band of the local hour that contains `local`, which must be timezone-aware."""
        if local.tzinfo is None:
            raise ValueError("band_for needs a timezone-aware datetime in local time")
        hour = local.hour
        if hour < VALLE_END_HOUR:
            return "valle"
        if self.is_business_day(local.date()) and tariff.peak_start <= hour < tariff.peak_end:
            return "punta"
        return "llano"

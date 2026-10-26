"""UTE triple-hour tariff: versioned tariffs, holidays and the Valle/Llano/Punta band of an hour."""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, get_args

import yaml

Band = Literal["valle", "llano", "punta"]
BANDS: tuple[Band, ...] = get_args(Band)

# Valle is always 00:00 - 07:00 (UTE Plan Inteligente Hogares, triple horario).
VALLE_END_HOUR = 7


class ConfigError(ValueError):
    """A configuration file is missing or invalid."""


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


def _read_yaml(path: Path) -> Any:
    if not path.exists():
        raise ConfigError(f"Missing configuration file: {path}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc


def _as_date(value: Any, where: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ConfigError(f"{where}: '{value}' is not a valid date (use YYYY-MM-DD)") from exc


def load_tariffs(path: Path) -> list[Tariff]:
    data = _read_yaml(path)
    entries = data.get("tariffs") if isinstance(data, dict) else None
    if not entries:
        raise ConfigError(f"{path}: expected a non-empty 'tariffs' list")

    tariffs: list[Tariff] = []
    for i, entry in enumerate(entries):
        where = f"{path} tariffs[{i}]"
        try:
            valid_from = _as_date(entry["valid_from"], where)
            vat = float(entry["vat"])
            start = int(entry["peak_window"]["start"])
            end = int(entry["peak_window"]["end"])
            rates = {band: float(entry["rates"][band]) for band in BANDS}
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"{where}: missing or invalid field ({exc!r})") from exc
        if vat < 1:
            raise ConfigError(f"{where}: vat must be a multiplier >= 1 (e.g. 1.22)")
        if not 0 <= start < end <= 24:
            raise ConfigError(f"{where}: peak_window must satisfy 0 <= start < end <= 24")
        if any(rate <= 0 for rate in rates.values()):
            raise ConfigError(f"{where}: all rates must be positive")
        tariffs.append(Tariff(valid_from, vat, start, end, rates))

    tariffs.sort(key=lambda t: t.valid_from)
    dates = [t.valid_from for t in tariffs]
    if len(set(dates)) != len(dates):
        raise ConfigError(f"{path}: two tariffs share the same valid_from date")
    return tariffs


def load_holidays(path: Path) -> dict[int, dict[date, str]]:
    data = _read_yaml(path)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a mapping of year -> list of holidays")

    holidays: dict[int, dict[date, str]] = {}
    for year_key, entries in data.items():
        try:
            year = int(year_key)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{path}: '{year_key}' is not a valid year") from exc
        days: dict[date, str] = {}
        for i, entry in enumerate(entries or []):
            where = f"{path} {year}[{i}]"
            try:
                day = _as_date(entry["date"], where)
                name = str(entry.get("name", ""))
            except (KeyError, TypeError, AttributeError) as exc:
                raise ConfigError(f"{where}: each holiday needs a 'date'") from exc
            if day.year != year:
                raise ConfigError(f"{where}: {day} is not in {year}")
            days[day] = name
        holidays[year] = days
    return holidays


def load_billing_config(config_dir: Path) -> BillingConfig:
    return BillingConfig(
        tariffs=load_tariffs(config_dir / "tariffs.yaml"),
        holidays=load_holidays(config_dir / "holidays.yaml"),
    )

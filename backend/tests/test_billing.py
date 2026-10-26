from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.billing import (
    BillingConfig,
    ConfigError,
    Tariff,
    load_billing_config,
    load_holidays,
    load_tariffs,
)

from .conftest import CONFIG_DIR

TZ = ZoneInfo("America/Montevideo")

TARIFF = Tariff(date(2026, 1, 1), 1.22, 17, 21, {"punta": 12.034, "llano": 5.172, "valle": 2.443})


@pytest.fixture
def cfg() -> BillingConfig:
    return BillingConfig(tariffs=[TARIFF], holidays={2026: {date(2026, 10, 12): "Día de la Raza"}})


def band(cfg: BillingConfig, y: int, m: int, d: int, h: int) -> str:
    return cfg.band_for(datetime(y, m, d, h, tzinfo=TZ), TARIFF)


def test_weekday_bands_with_peak_17_to_21(cfg: BillingConfig) -> None:
    # Thursday 22 October 2026, a normal business day
    assert [band(cfg, 2026, 10, 22, h) for h in (0, 6)] == ["valle", "valle"]
    assert [band(cfg, 2026, 10, 22, h) for h in (7, 12, 16)] == ["llano"] * 3
    assert [band(cfg, 2026, 10, 22, h) for h in (17, 18, 20)] == ["punta"] * 3
    assert [band(cfg, 2026, 10, 22, h) for h in (21, 23)] == ["llano", "llano"]


def test_weekend_has_no_punta(cfg: BillingConfig) -> None:
    # Saturday 24 October 2026
    assert band(cfg, 2026, 10, 24, 18) == "llano"
    assert band(cfg, 2026, 10, 24, 3) == "valle"


def test_holiday_has_no_punta(cfg: BillingConfig) -> None:
    # Monday 12 October 2026 is Día de la Raza
    assert cfg.is_holiday(date(2026, 10, 12))
    assert band(cfg, 2026, 10, 12, 18) == "llano"


def test_rates_include_vat() -> None:
    assert TARIFF.rate("punta") == pytest.approx(12.034)
    assert TARIFF.rate_with_vat("punta") == pytest.approx(12.034 * 1.22)
    assert TARIFF.rate_with_vat("valle") == pytest.approx(2.443 * 1.22)


def test_tariff_in_force_depends_on_the_date() -> None:
    old = Tariff(date(2026, 1, 1), 1.22, 17, 21, {"punta": 12.0, "llano": 5.0, "valle": 2.0})
    new = Tariff(date(2027, 1, 1), 1.22, 18, 22, {"punta": 13.0, "llano": 5.5, "valle": 2.2})
    cfg = BillingConfig(tariffs=[old, new], holidays={})

    assert cfg.tariff_for(date(2025, 12, 31)) is None
    assert cfg.tariff_for(date(2026, 12, 31)) is old
    assert cfg.tariff_for(date(2027, 1, 1)) is new
    # the new tariff also moves the peak window
    assert cfg.band_for(datetime(2027, 1, 5, 21, tzinfo=TZ), new) == "punta"
    assert cfg.band_for(datetime(2026, 1, 6, 21, tzinfo=TZ), old) == "llano"


def test_missing_holiday_year_is_detected(cfg: BillingConfig) -> None:
    assert cfg.has_holidays_for(2026)
    assert not cfg.has_holidays_for(2027)


def test_naive_datetime_is_rejected(cfg: BillingConfig) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        cfg.band_for(datetime(2026, 10, 22, 18), TARIFF)


VALID_TARIFF = """  - valid_from: {valid_from}
    vat: {vat}
    peak_window: {{start: {start}, end: {end}}}
    rates: {{punta: {punta}, llano: 1, valle: 1}}
"""


def write_tariffs(tmp_path: Path, *entries: str) -> Path:
    path = tmp_path / "tariffs.yaml"
    path.write_text("tariffs:\n" + "".join(entries), encoding="utf-8")
    return path


def tariff_entry(
    valid_from: str = "2026-01-01",
    vat: float = 1.22,
    start: int = 17,
    end: int = 21,
    punta: float = 1,
) -> str:
    return VALID_TARIFF.format(valid_from=valid_from, vat=vat, start=start, end=end, punta=punta)


def test_real_config_loads() -> None:
    config = load_billing_config(CONFIG_DIR)

    tariff = config.tariff_for(date(2026, 10, 22))
    assert tariff is not None
    assert tariff.rate("punta") == pytest.approx(12.034)
    assert config.is_holiday(date(2026, 10, 12))
    assert not config.has_holidays_for(2027)


def test_tariffs_are_sorted_by_valid_from(tmp_path: Path) -> None:
    path = write_tariffs(tmp_path, tariff_entry("2027-01-01"), tariff_entry("2026-01-01"))

    assert [t.valid_from for t in load_tariffs(path)] == [date(2026, 1, 1), date(2027, 1, 1)]


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Missing"):
        load_tariffs(tmp_path / "tariffs.yaml")


def test_invalid_yaml_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "tariffs.yaml"
    path.write_text("tariffs: [unclosed", encoding="utf-8")

    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_tariffs(path)


def test_empty_tariffs_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "tariffs.yaml"
    path.write_text("tariffs: []\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="non-empty"):
        load_tariffs(path)


def test_invalid_vat_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="vat"):
        load_tariffs(write_tariffs(tmp_path, tariff_entry(vat=0.5)))


def test_invalid_peak_window_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="peak_window"):
        load_tariffs(write_tariffs(tmp_path, tariff_entry(start=21, end=17)))


def test_non_positive_rate_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="positive"):
        load_tariffs(write_tariffs(tmp_path, tariff_entry(punta=0)))


def test_duplicate_valid_from_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="same valid_from"):
        load_tariffs(write_tariffs(tmp_path, tariff_entry(), tariff_entry()))


def test_holiday_outside_its_year_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "holidays.yaml"
    path.write_text("2026:\n  - { date: 2027-01-01, name: Año Nuevo }\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="not in 2026"):
        load_holidays(path)

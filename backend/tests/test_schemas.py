from datetime import UTC, date, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas import (
    BucketOut,
    ConsumptionResponse,
    MissingHolidaysWarning,
    NoTariffWarning,
    OutletValue,
    Warning_,
)

WARNING = TypeAdapter(Warning_)


def test_warning_class_is_chosen_by_code() -> None:
    assert WARNING.validate_python({"code": "missing_holidays", "year": 2027}) == MissingHolidaysWarning(year=2027)
    assert WARNING.validate_python({"code": "no_tariff", "since": "2025-01-01"}) == NoTariffWarning(
        since=date(2025, 1, 1)
    )


def test_warning_cannot_mix_fields_of_the_other_kind() -> None:
    with pytest.raises(ValidationError):
        WARNING.validate_python({"code": "missing_holidays", "year": 2027, "since": "2025-01-01"})
    with pytest.raises(ValidationError):
        WARNING.validate_python({"code": "no_tariff", "year": 2027})


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        OutletValue.model_validate({"kwh": 1.0, "cost": 2.0, "extra": 3})


def test_bucket_json_has_the_expected_keys() -> None:
    bucket = BucketOut(
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        has_data=True,
        partial=False,
        outlets={1: OutletValue(kwh=1.5, cost=10.0)},
    )
    data = bucket.model_dump(mode="json")
    assert set(data) == {"start", "end", "has_data", "partial", "band", "rate_per_kwh", "outlets"}
    assert data["band"] is None
    assert data["outlets"] == {"1": {"kwh": 1.5, "cost": 10.0}}


def test_response_accepts_both_warning_kinds() -> None:
    response = ConsumptionResponse.model_validate(
        {
            "granularity": "day",
            "timezone": "America/Montevideo",
            "outlets": [],
            "buckets": [],
            "totals": {},
            "warnings": [
                {"code": "missing_holidays", "year": 2027},
                {"code": "no_tariff", "since": "2025-01-01"},
            ],
        }
    )
    first, second = response.warnings
    assert isinstance(first, MissingHolidaysWarning)
    assert isinstance(second, NoTariffWarning)

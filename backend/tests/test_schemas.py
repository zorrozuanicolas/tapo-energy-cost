import json
from datetime import UTC, date, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from app.live import LiveReading
from app.schemas import (
    BucketOut,
    ConsumptionResponse,
    LiveOut,
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


def test_live_event_json_has_the_expected_keys() -> None:
    event = LiveOut(outlet_id=1, power_w=42.5, online=True, ts=datetime(2026, 11, 4, 12, 0, tzinfo=UTC))

    assert json.loads(event.model_dump_json()) == {
        "outlet_id": 1,
        "power_w": 42.5,
        "online": True,
        "ts": "2026-11-04T12:00:00Z",
    }


def test_offline_live_event_has_a_null_power() -> None:
    event = LiveOut(outlet_id=1, power_w=None, online=False, ts=datetime(2026, 11, 4, 12, 0, tzinfo=UTC))

    assert json.loads(event.model_dump_json())["power_w"] is None


def test_live_event_copies_every_field_of_a_reading() -> None:
    ts = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)

    event = LiveOut.from_reading(LiveReading(outlet_id=3, power_w=7.0, online=True, ts=ts))

    assert event == LiveOut(outlet_id=3, power_w=7.0, online=True, ts=ts)


def test_unknown_field_of_a_live_event_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LiveOut.model_validate(
            {"outlet_id": 1, "power_w": 1.0, "online": True, "ts": "2026-11-04T12:00:00Z", "x": 1}
        )

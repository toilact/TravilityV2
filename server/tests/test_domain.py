import pytest
from pydantic import ValidationError

from app.domain import Draft, Trip


def test_trip_defaults():
    t = Trip(destination="da-lat", days=3, budget=3_000_000)
    assert (t.travelers, t.pace, t.travel_mode, t.start_date) == (1, "vua", "xe-may", None)


def test_trip_drops_unknown_tags():
    t = Trip(destination="da-lat", days=1, budget=1, required_tags=["an-chay", "khong-ton-tai"])
    assert t.required_tags == ["an-chay"]


@pytest.mark.parametrize("days", [0, 8])
def test_trip_days_range(days):
    with pytest.raises(ValidationError):
        Trip(destination="da-lat", days=days, budget=1)


def test_draft_rejects_bad_time():
    with pytest.raises(ValidationError):
        Draft.model_validate(
            {"days": [{"stops": [{"place_id": 1, "start_time": "25:00", "duration_min": 60}]}]}
        )

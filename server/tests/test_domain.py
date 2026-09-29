import pytest
from pydantic import ValidationError

from app.domain import Draft, Trip, TripAnswers


def test_trip_defaults():
    t = Trip(destination="da-lat", days=3, budget=3_000_000)
    assert (t.travelers, t.pace, t.travel_mode, t.start_date) == (1, "vua", None, None)
    assert (t.arrival_time, t.departure_time, t.arrival_mode) == (None, None, None)


def test_one_day_departure_must_be_after_arrival():
    with pytest.raises(ValidationError, match="Giờ về phải sau giờ đến"):
        Trip(destination="da-lat", days=1, budget=1, arrival_time="15:00", departure_time="09:00")


def test_multi_day_departure_may_be_earlier_clock_time():
    t = Trip(destination="da-lat", days=2, budget=1, arrival_time="15:00", departure_time="09:00")
    assert t.departure_time == "09:00"


def test_trip_rejects_bad_time():
    with pytest.raises(ValidationError):
        Trip(destination="da-lat", days=1, budget=1, arrival_time="2pm")


def test_own_vehicle_modes_accepted():
    assert Trip(destination="da-lat", days=1, budget=1, travel_mode="o-to-rieng").travel_mode == "o-to-rieng"


def test_answers_all_optional():
    assert TripAnswers().model_dump(exclude_none=True) == {}


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

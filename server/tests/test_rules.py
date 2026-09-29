import datetime as dt

import pytest

from app.domain import Draft, Hub, Place, Trip
from app.rules import InvalidDraft, build_itinerary, is_open, make_leg

WEEK = {d: ["08:00", "17:00"] for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}


def P(id, kind="tham-quan", price=0, lat=11.94, lon=108.44, outdoor=False, tags=(), hours=None):
    return Place(id=id, destination="da-lat", name=f"P{id}", kind=kind, lat=lat, lon=lon,
                 price=price, open_hours=WEEK if hours is None else hours, outdoor=outdoor,
                 tags=list(tags))


def draft(days, stay=None, start="09:00"):
    return Draft.model_validate({"stay_place_id": stay, "summary": "", "days": [
        {"stops": [{"place_id": pid, "start_time": start, "duration_min": 60} for pid in day]}
        for day in days]})


def test_short_leg_is_walk():
    leg = make_leg(P(1), P(2, lat=11.9401), "xe-may", 1)
    assert (leg.mode, leg.cost) == ("walk", 0)


def test_motorbike_leg_cost():
    leg = make_leg(P(1), P(2, lat=12.04), "xe-may", 1)  # ~0.1° vĩ độ ≈ 11.1 km × 1.3
    assert leg.mode == "xe-may"
    assert leg.distance_km == pytest.approx(14.46, abs=0.05)
    assert leg.cost == round(leg.distance_km * 2_000)


def test_total_cost():
    # 2 ngày, 2 người: Stay 500k × 1 phòng × 1 đêm + thuê 1 xe × 2 ngày + Stop × 2 người; Leg = 0 (cùng tọa độ)
    places = {1: P(1, price=50_000), 2: P(2, price=30_000), 9: P(9, kind="cho-o", price=500_000, hours={})}
    trip = Trip(destination="da-lat", days=2, travelers=2, budget=10_000_000)
    itin = build_itinerary(trip, draft([[1], [2]], stay=9), places)
    assert itin.total_cost == 500_000 + 240_000 + 100_000 + 60_000
    assert [len(d.legs) for d in itin.days] == [2, 2]  # Stay → Stop → Stay
    assert itin.conflicts == []


def test_unknown_place_rejected():
    with pytest.raises(InvalidDraft, match="999"):
        build_itinerary(Trip(destination="da-lat", days=1, budget=1), draft([[999]]), {1: P(1)})


def test_multi_day_requires_stay():
    with pytest.raises(InvalidDraft, match="stay_place_id"):
        build_itinerary(Trip(destination="da-lat", days=2, budget=1), draft([[1], [1]]), {1: P(1)})


def test_over_budget_still_returns_itinerary():
    itin = build_itinerary(Trip(destination="da-lat", days=1, budget=10_000, travel_mode="grab"),
                           draft([[1]]), {1: P(1, price=50_000)})
    assert [c.kind for c in itin.conflicts] == ["over_budget"]
    assert "40.000đ" in itin.conflicts[0].message


def test_closed_on_that_weekday():
    monday = dt.date(2026, 10, 5)
    assert monday.weekday() == 0
    closed_monday = {**WEEK, "mon": None}
    trip = Trip(destination="da-lat", days=1, budget=10**9, start_date=monday, travel_mode="grab")
    itin = build_itinerary(trip, draft([[1]]), {1: P(1, hours=closed_monday)})
    assert [c.kind for c in itin.conflicts] == ["closed"]


def test_without_date_closed_only_if_never_open():
    trip = Trip(destination="da-lat", days=1, budget=10**9, travel_mode="grab")
    ok = build_itinerary(trip, draft([[1]]), {1: P(1, hours={**WEEK, "mon": None})})
    assert ok.conflicts == []
    night = {d: ["18:00", "23:00"] for d in WEEK}
    bad = build_itinerary(trip, draft([[1]]), {1: P(1, hours=night)})
    assert [c.kind for c in bad.conflicts] == ["closed"]


def test_overnight_hours():
    bar = P(1, hours={d: ["18:00", "02:00"] for d in WEEK})
    assert is_open(bar, "mon", "22:00", 60)


def test_rain_outdoor_conflict():
    trip = Trip(destination="da-lat", days=1, budget=10**9, travel_mode="grab")
    itin = build_itinerary(trip, draft([[1]]), {1: P(1, outdoor=True)}, rain=[80])
    assert [c.kind for c in itin.conflicts] == ["rain_outdoor"]
    assert itin.days[0].rain_chance == 80


def test_missing_required_tag():
    trip = Trip(destination="da-lat", days=1, budget=10**9, required_tags=["an-chay"], travel_mode="grab")
    itin = build_itinerary(trip, draft([[1]]), {1: P(1, tags=["cafe-chill"])})
    assert [c.kind for c in itin.conflicts] == ["missing_tag"]


HUB = Hub(name="Sân bay Liên Khương", lat=11.75, lon=108.37)
STAY = {9: P(9, kind="cho-o", hours={})}


def test_unset_travel_mode_defaults_to_rented_motorbike():
    trip = Trip(destination="da-lat", days=1, budget=10**9)
    assert build_itinerary(trip, draft([[1]]), {1: P(1)}).total_cost == 120_000


def test_own_motorbike_has_no_rent():
    trip = Trip(destination="da-lat", days=1, travelers=2, budget=10**9, travel_mode="xe-may-rieng")
    assert build_itinerary(trip, draft([[1]]), {1: P(1)}).total_cost == 0


def test_own_car_leg_is_one_car_fuel():
    leg = make_leg(P(1), P(2, lat=12.04), "o-to-rieng", 5)
    assert leg.mode == "o-to"
    assert leg.cost == round(leg.distance_km * 3_500)


def test_own_car_pays_parking_per_day():
    trip = Trip(destination="da-lat", days=2, travelers=5, budget=10**9, travel_mode="o-to-rieng")
    itin = build_itinerary(trip, draft([[1], [1]], stay=9), {1: P(1), **STAY})
    assert itin.total_cost == 2 * 50_000


def test_hub_starts_first_day_and_ends_last_day():
    trip = Trip(destination="da-lat", days=2, budget=10**9, travel_mode="grab")
    itin = build_itinerary(trip, draft([[1], [2]], stay=9), {1: P(1), 2: P(2), **STAY}, hub=HUB)
    d1, d2 = itin.days
    assert (d1.legs[0].from_place_id, d1.legs[-1].to_place_id) == (None, 9)
    assert (d2.legs[0].from_place_id, d2.legs[-1].to_place_id) == (9, None)
    assert d1.legs[0].mode == "grab" and d1.legs[0].distance_km > 20


def test_hub_without_stay_one_day():
    trip = Trip(destination="da-lat", days=1, budget=10**9, travel_mode="grab")
    legs = build_itinerary(trip, draft([[1]]), {1: P(1)}, hub=HUB).days[0].legs
    assert [(leg.from_place_id, leg.to_place_id) for leg in legs] == [(None, 1), (1, None)]


def test_late_arrival_still_returns_itinerary_with_conflict():
    trip = Trip(destination="da-lat", days=1, budget=10**9, travel_mode="grab", arrival_time="20:00")
    itin = build_itinerary(trip, draft([[1]]), {1: P(1)})  # Stop 09:00
    assert [c.kind for c in itin.conflicts] == ["before_arrival"]
    assert "20:00" in itin.conflicts[0].message


def test_stop_after_arrival_buffer_is_fine():
    trip = Trip(destination="da-lat", days=1, budget=10**9, travel_mode="grab", arrival_time="14:00")
    assert build_itinerary(trip, draft([[1]], start="15:00"), {1: P(1)}).conflicts == []


def test_stop_too_close_to_departure_on_last_day():
    trip = Trip(destination="da-lat", days=2, budget=10**9, travel_mode="grab", departure_time="11:00")
    itin = build_itinerary(trip, draft([[1], [1]], stay=9), {1: P(1), **STAY})  # 09:00–10:00 > 11:00 − 90'
    assert [(c.kind, c.day_index) for c in itin.conflicts] == [("after_departure", 1)]

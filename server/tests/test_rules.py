import datetime as dt

import pytest

from app.domain import Draft, Place, Trip
from app.rules import InvalidDraft, build_itinerary, is_open, make_leg

WEEK = {d: ["08:00", "17:00"] for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}


def P(id, kind="tham-quan", price=0, lat=11.94, lon=108.44, outdoor=False, tags=(), hours=None):
    return Place(id=id, destination="da-lat", name=f"P{id}", kind=kind, lat=lat, lon=lon,
                 price=price, open_hours=WEEK if hours is None else hours, outdoor=outdoor,
                 tags=list(tags))


def draft(days, stay=None):
    return Draft.model_validate({"stay_place_id": stay, "summary": "", "days": [
        {"stops": [{"place_id": pid, "start_time": "09:00", "duration_min": 60} for pid in day]}
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

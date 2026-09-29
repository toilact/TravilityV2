from app.domain import WEEKDAYS, Draft, Place, Trip
from app.followup import itinerary_facts
from app.rules import build_itinerary, cost_breakdown

WEEK = {d: ["08:00", "22:00"] for d in WEEKDAYS}
TRIP = Trip(destination="da-lat", days=2, budget=5_000_000, travelers=2, travel_mode="xe-may")


def P(id, kind="cafe", price=0, lat=11.94, outdoor=False):
    return Place(id=id, destination="da-lat", name=f"P{id}", kind=kind, lat=lat, lon=108.44, price=price,
                 open_hours=WEEK, outdoor=outdoor, tags=[])


PLACES = {1: P(1, "an-uong", 50_000), 2: P(2, "tham-quan", 100_000, lat=11.96, outdoor=True),
          3: P(3, "cafe", 40_000), 9: P(9, "cho-o", 500_000, lat=11.95)}


def itin(pinned=()):
    draft = Draft.model_validate({"stay_place_id": 9, "summary": "", "days": [
        {"stops": [{"place_id": 1, "start_time": "08:00", "duration_min": 60},
                   {"place_id": 2, "start_time": "10:00", "duration_min": 90, "pinned": 2 in pinned}]},
        {"stops": [{"place_id": 3, "start_time": "09:00", "duration_min": 60}]}]})
    return build_itinerary(TRIP, draft, PLACES)


def test_cost_breakdown_sums_to_total():
    it = itin()
    b = cost_breakdown(TRIP, it, PLACES)
    assert b["an_uong"] == (50_000 + 40_000) * 2
    assert b["tham_quan"] == 100_000 * 2
    assert b["cho_o"] == 500_000 * 1 * 1  # 1 phòng × 1 đêm
    assert sum(b.values()) == it.total_cost


def test_facts_have_code_computed_numbers_and_indexes():
    it = itin(pinned={2})
    km = sum(leg.distance_km for d in it.days for leg in d.legs)
    facts = itinerary_facts(TRIP, it, PLACES)
    assert f"{km:.1f} km" in facts
    assert "[0.1]" in facts and "đã ghim" in facts
    assert "không có dự báo" in facts  # Trip không có ngày đi
    assert "nhiệt độ" in facts  # nói rõ app không có dữ liệu này

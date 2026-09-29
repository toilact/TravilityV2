import pytest

from app.domain import WEEKDAYS, Disruption, Draft, Place, Trip
from app.replan import InvalidDisruption, NoFeasible, propose
from app.rules import build_itinerary

WEEK = {d: ["08:00", "22:00"] for d in WEEKDAYS}
TRIP = Trip(destination="da-lat", days=1, budget=5_000_000, travel_mode="grab",
            preferred_tags=["cafe-chill", "lich-su"])


def P(id, kind="cafe", tags=(), price=0, lat=11.94, hours=None):
    return Place(id=id, destination="da-lat", name=f"P{id}", kind=kind, lat=lat, lon=108.44, price=price,
                 open_hours=WEEK if hours is None else hours, outdoor=False, tags=list(tags))


def setup(stops, trip=TRIP, pinned=()):
    """stops: [(Place, 'HH:MM')] → (places, Itinerary 1 ngày, mỗi Stop 60′)."""
    places = {p.id: p for p, _ in stops}
    draft = Draft.model_validate({"summary": "", "days": [{"stops": [
        {"place_id": p.id, "start_time": t, "duration_min": 60, "pinned": p.id in pinned} for p, t in stops]}]})
    return places, build_itinerary(trip, draft, places)


def cands(*ps, seen=None):
    def fn(lost, used):
        if seen is not None:
            seen.update(used)
        return [p for p in ps if p.id not in used]
    return fn


def closed(stop=0, kind="closed"):
    return Disruption(kind=kind, day_index=0, stop_index=stop)


LOST, MUSEUM = P(1, tags=["cafe-chill"]), P(2, kind="tham-quan", tags=["lich-su"])


def test_same_intent_ranks_first_and_other_stops_untouched():
    places, itin = setup([(LOST, "09:00"), (MUSEUM, "11:00")])
    same, other = P(10, tags=["cafe-chill", "yen-tinh"]), P(11, tags=["check-in"])
    opts = propose(TRIP, itin, places, closed(), cands(other, same))
    assert [o.added[0].id for o in opts] == [10, 11]
    assert opts[0].reason_codes[0] == "INTENT_MATCH"
    assert opts[0].metrics["intents_kept"] == ["thu-gian"]
    assert opts[1].metrics["intents_lost"] == ["thu-gian"]
    assert opts[0].changed == [(0, 0)]
    assert opts[0].itinerary.days[0].stops[1].place_id == 2
    assert "Giữ mục đích Thư giãn" in opts[0].explanation


def test_at_most_three_distinct_and_used_places_excluded():
    places, itin = setup([(LOST, "09:00"), (MUSEUM, "11:00")])
    seen = set()
    opts = propose(TRIP, itin, places, closed(kind="disliked"), cands(*[P(i) for i in range(10, 15)], seen=seen))
    assert seen == {1, 2}
    assert len(opts) == 3
    assert len({o.added[0].id for o in opts}) == 3
    assert "bạn muốn đổi" in opts[0].itinerary.days[0].stops[0].reason


def test_closed_at_that_time_is_skipped():
    places, itin = setup([(LOST, "09:00")])
    late_opener = P(10, hours={d: ["14:00", "22:00"] for d in WEEKDAYS})
    assert propose(TRIP, itin, places, closed(), cands(late_opener)) == NoFeasible(reason_codes=["NO_OPEN_CANDIDATE"])
    opts = propose(TRIP, itin, places, closed(), cands(late_opener, P(11)))
    assert [o.added[0].id for o in opts] == [11]


def test_no_candidate():
    places, itin = setup([(LOST, "09:00")])
    assert propose(TRIP, itin, places, closed(), cands()) == NoFeasible(reason_codes=["NO_CANDIDATE"])


def test_too_far_to_reach_next_stop_in_time():
    places, itin = setup([(MUSEUM, "09:00"), (LOST, "10:05")])
    far = P(10, lat=12.2)  # ~37 km bằng Grab ≈ 90 phút, khoảng trống chỉ 5 phút
    got = propose(TRIP, itin, places, closed(stop=1), cands(far))
    assert got == NoFeasible(reason_codes=["NOT_REACHABLE_IN_TIME"])


def test_new_over_budget_is_rejected():
    trip = Trip(destination="da-lat", days=1, budget=100_000, travel_mode="grab")
    places, itin = setup([(P(1, price=50_000), "09:00")], trip=trip)
    got = propose(trip, itin, places, closed(), cands(P(10, price=500_000)))
    assert got == NoFeasible(reason_codes=["OVER_BUDGET"])


def test_pinned_or_missing_stop_is_invalid():
    places, itin = setup([(LOST, "09:00")], pinned={1})
    with pytest.raises(InvalidDisruption):
        propose(TRIP, itin, places, closed(), cands(P(10)))
    with pytest.raises(InvalidDisruption):
        propose(TRIP, itin, places, closed(stop=5), cands(P(10)))


def test_explanation_from_numbers_without_percent():
    places, itin = setup([(P(1, tags=["cafe-chill"], price=20_000), "09:00")])
    opts = propose(TRIP, itin, places, closed(), cands(P(10, tags=["cafe-chill"], price=50_000)))
    assert opts[0].metrics["cost_delta"] == 30_000
    assert "đắt hơn 30.000đ" in opts[0].explanation
    assert "%" not in opts[0].explanation
    assert "PRICIER" in opts[0].reason_codes


def test_lost_place_without_intent():
    places, itin = setup([(P(1, tags=["gia-re"]), "09:00")])
    opts = propose(TRIP, itin, places, closed(), cands(P(10, tags=["gia-re"])))
    assert not any(c.startswith("INTENT_") for c in opts[0].reason_codes)
    assert "mục đích" not in opts[0].explanation


def test_intent_still_covered_elsewhere_is_not_reported_lost():
    other_cafe = P(3, tags=["cafe-chill"])
    places, itin = setup([(LOST, "09:00"), (MUSEUM, "11:00"), (other_cafe, "14:00")])
    opts = propose(TRIP, itin, places, closed(), cands(P(10, tags=["check-in"])))
    assert opts[0].metrics["intents_lost"] == []
    assert "không còn" not in opts[0].explanation


def test_only_trip_intents_are_mentioned():
    places, itin = setup([(P(1, tags=["cafe-chill", "check-in"]), "09:00")])
    opts = propose(TRIP, itin, places, closed(), cands(P(10, tags=["cafe-chill"])))
    assert opts[0].reason_codes[0] == "INTENT_MATCH"
    assert "Vui chơi" not in opts[0].explanation

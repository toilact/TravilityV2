from app.agent import plan
from app.domain import Trip
from tests.fakes import FakeClient, reply
from tests.helpers import add_place, unit_vec


def fake_embed(texts):
    return [unit_vec(0) for _ in texts]


def stops(*ids):
    return {"summary": "Lịch trình thử", "days": [{"stops": [
        {"place_id": pid, "start_time": f"{9 + i:02d}:00", "duration_min": 60, "reason": "hợp sở thích"}
        for i, pid in enumerate(ids)]}]}


def run(conn, responses, budget=10_000_000):
    client = FakeClient(responses)
    trip = Trip(destination="da-lat", days=1, budget=budget, travel_mode="grab")
    return client, list(plan(conn, client, "m", trip, fake_embed, None))


def tool_messages(client):
    return [m["content"] for m in client.calls[-1]["messages"] if m.get("role") == "tool"]


def test_happy_path(conn):
    a, b = add_place(conn, name="Cafe", kind="cafe"), add_place(conn, name="Hồ", vec=1)
    _, events = run(conn, [reply(("search_places", {"query": "cafe"})),
                           reply(("submit_itinerary", stops(a, b)))])
    assert [e["type"] for e in events] == ["tool_call", "itinerary"]
    assert {p["id"] for p in events[0]["places"]} == {a, b}
    itin = events[-1]["itinerary"]
    assert [s["place_id"] for s in itin["days"][0]["stops"]] == [a, b]
    assert set(events[-1]["places"]) == {str(a), str(b)}


def test_unseen_place_rejected_then_retry(conn):
    a = add_place(conn)
    client, events = run(conn, [reply(("search_places", {"query": "x"})),
                                reply(("submit_itinerary", stops(999))),
                                reply(("submit_itinerary", stops(a)))])
    assert events[-1]["type"] == "itinerary"
    assert any(m.startswith("Lỗi") and "999" in m for m in tool_messages(client))


def test_place_not_searched_is_rejected(conn):
    a = add_place(conn)  # có trong DB nhưng AI chưa search → vẫn bị từ chối
    _, events = run(conn, [reply(("submit_itinerary", stops(a))),
                           reply(("submit_itinerary", stops(a)))])
    assert events[-1]["type"] == "error"


def test_gives_up_after_two_invalid(conn):
    add_place(conn)
    _, events = run(conn, [reply(("search_places", {"query": "x"})),
                           reply(("submit_itinerary", stops(999))),
                           reply(("submit_itinerary", stops(998)))])
    assert events[-1]["type"] == "error"


def test_malformed_arguments_do_not_crash(conn):
    a = add_place(conn)
    client, events = run(conn, [reply(("search_places", "{hỏng")),
                                reply(("search_places", {"query": "x"})),
                                reply(("submit_itinerary", stops(a)))])
    assert events[-1]["type"] == "itinerary"
    assert any("JSON" in m for m in tool_messages(client))


def test_conflict_gets_one_resubmit_then_accepted(conn):
    a = add_place(conn, price=500_000)
    client, events = run(conn, [reply(("search_places", {"query": "x"})),
                                reply(("submit_itinerary", stops(a))),
                                reply(("submit_itinerary", stops(a)))], budget=1_000)
    assert [c["kind"] for c in events[-1]["itinerary"]["conflicts"]] == ["over_budget"]
    assert any(m.startswith("Conflict") for m in tool_messages(client))


def test_thinking_text_is_streamed(conn):
    a = add_place(conn)
    _, events = run(conn, [reply(("search_places", {"query": "x"}), content="Để mình tìm quán cafe"),
                           reply(("submit_itinerary", stops(a)))])
    assert events[0] == {"type": "thinking", "text": "Để mình tìm quán cafe"}

from contextlib import nullcontext

import pytest

from app import multi, rules
from app.domain import Trip
from tests.fakes import RoleClient, reply
from tests.helpers import add_place, unit_vec

FOOD, SIGHT, STAY = "chuyên gia Ăn uống", "chuyên gia Tham quan", "chuyên gia Chỗ ở"
SYNTH = "trợ lý lập lịch trình"
SEARCH = reply(("search_places", {"query": "x"}))


@pytest.fixture(autouse=True)
def env(conn, monkeypatch):
    monkeypatch.setattr(rules, "MEALS", ())


def fake_embed(texts):
    return [unit_vec(0) for _ in texts]


def trip(days=1):
    return Trip(destination="da-lat", days=days, budget=10_000_000, travel_mode="grab")


def pick(*ids, note="ghi chú"):
    return reply(("submit_shortlist", {"place_ids": list(ids), "note": note}))


def one(conn, role, responses):
    events, client = [], RoleClient({"chuyên gia": responses})
    return client, events, multi.shortlist(conn, client, "m", trip(), role, fake_embed, None, [], events.append)


def test_roles_skip_stay_for_one_day_trip():
    assert multi.roles_for(trip(1)) == ["an-uong", "tham-quan"]
    assert multi.roles_for(trip(2)) == ["an-uong", "tham-quan", "cho-o"]


def test_wanted_follows_meals_and_pace():
    t = trip(2)  # Pace vừa: 5 Stop/ngày, 3 bữa/ngày
    assert [multi.wanted(t, r) for r in ("an-uong", "tham-quan", "cho-o")] == [12, 8, 3]


def test_specialist_returns_places_it_searched(conn):
    food = add_place(conn, "Quán", "an-uong")
    add_place(conn, "Cafe", "cafe")
    client, events, out = one(conn, "an-uong", [SEARCH, pick(food)])
    assert out == {"role": "an-uong", "place_ids": [food], "note": "ghi chú"}
    assert events[0]["type"] == "tool_call" and events[0]["agent"] == "an-uong"
    assert [p["id"] for p in events[0]["places"]] == [food]  # code ép kind theo role
    assert "Ăn uống" in client.calls[0]["messages"][0]["content"]


def test_specialist_cannot_pick_another_roles_kind(conn):
    food, stay = add_place(conn, "Quán", "an-uong"), add_place(conn, "Khách sạn", "cho-o")
    _, _, out = one(conn, "an-uong", [reply(("search_places", {"query": "x", "kind": "cho-o"})), pick(stay, food)])
    assert out["place_ids"] == [food]


def test_sightseeing_role_takes_cafe_but_not_food(conn):
    cafe, food = add_place(conn, "Cafe", "cafe"), add_place(conn, "Quán", "an-uong")
    _, _, out = one(conn, "tham-quan", [reply(("search_places", {"query": "x", "kind": "an-uong"})), pick(cafe, food)])
    assert out["place_ids"] == [cafe]


def test_unknown_ids_dropped_and_empty_shortlist_fails(conn):
    add_place(conn, "Cafe", "cafe")
    with pytest.raises(multi.AgentFailed):
        one(conn, "tham-quan", [SEARCH] + [pick(999)] * 5)


def test_fifth_search_is_refused(conn):
    cafe = add_place(conn, "Cafe", "cafe")
    client, events, out = one(conn, "tham-quan", [SEARCH] * 5 + [pick(cafe)])
    assert len(events) == 4 and out["place_ids"] == [cafe]
    tool = [m["content"] for m in client.calls[-1]["messages"] if m.get("role") == "tool"]
    assert "hết lượt tìm" in tool[4]

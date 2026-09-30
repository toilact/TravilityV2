"""Ghim, xem version, lịch sử chat, quay lại bản cũ (spec revision-day-du)."""
from tests.test_trips_api import (auth, client, events, no_meal_rule, trip_with_itinerary,  # noqa: F401 (fixture)
                                  use_llm)
from tests.fakes import reply
from tests.helpers import add_place


def pin(client, h, tid, pid, pinned=True):
    return client.patch(f"/trips/{tid}/pins", headers=h, json={"place_id": pid, "pinned": pinned})


def test_pin_overlays_stop_and_lists_versions(client, conn, monkeypatch):
    h, tid, pid = trip_with_itinerary(client, conn, monkeypatch)
    r = pin(client, h, tid, pid)
    assert r.status_code == 200 and r.json() == {"pinned_place_ids": [pid]}
    got = client.get(f"/trips/{tid}", headers=h).json()
    assert got["itinerary"]["days"][0]["stops"][0]["pinned"] is True
    assert got["versions"] == [1] and got["pinned_place_ids"] == [pid]
    assert got["center"] == [108.44, 11.94]
    assert conn.execute("SELECT count(*) AS n FROM itineraries").fetchone()["n"] == 1  # ghim không tạo version


def test_unpin_is_idempotent(client, conn, monkeypatch):
    h, tid, pid = trip_with_itinerary(client, conn, monkeypatch)
    assert pin(client, h, tid, pid, False).json() == {"pinned_place_ids": []}
    pin(client, h, tid, pid)
    pin(client, h, tid, pid)  # ghim 2 lần không nhân đôi
    assert pin(client, h, tid, pid, False).json() == {"pinned_place_ids": []}


def test_pin_place_not_in_latest_is_422(client, conn, monkeypatch):
    h, tid, _ = trip_with_itinerary(client, conn, monkeypatch)
    other = add_place(conn, name="Không có trong lịch")
    r = pin(client, h, tid, other)
    assert r.status_code == 422 and "đang có trong lịch trình" in r.json()["detail"]


def test_get_old_version_and_missing_version(client, conn, monkeypatch):
    h, tid, pid = trip_with_itinerary(client, conn, monkeypatch)
    other = add_place(conn, name="Cafe rẻ", kind="cafe")
    use_llm(monkeypatch, [reply(("search_places", {"query": "cafe rẻ"})),
                          reply(("edit_itinerary", {"summary": "rẻ hơn", "ops": [
                              {"op": "replace_stop", "day": 1, "stop": 1, "place_id": other}]}))])
    events(client.post("/trips", json={"message": "rẻ hơn", "trip_id": tid}, headers=h))
    v1 = client.get(f"/trips/{tid}?version=1", headers=h).json()
    assert v1["version"] == 1 and v1["versions"] == [1, 2]
    assert v1["itinerary"]["days"][0]["stops"][0]["place_id"] == pid
    assert client.get(f"/trips/{tid}?version=9", headers=h).status_code == 404


def test_get_trip_without_itinerary(client, conn, monkeypatch):
    use_llm(monkeypatch, [reply(("record_trip", {"destination": "da-lat", "days": 1, "budget": 2_000_000}))])
    add_place(conn)
    h = auth(client)
    tid = events(client.post("/trips", json={"message": "Đà Lạt 1 ngày"}, headers=h))[-1]["trip_id"]
    got = client.get(f"/trips/{tid}", headers=h).json()
    assert (got["itinerary"], got["versions"], got["pinned_place_ids"]) == (None, [], [])
    assert client.get("/trips", headers=h).json()[0]["destination_name"] == "da-lat"


def test_pins_other_user_404(client, conn, monkeypatch):
    h, tid, pid = trip_with_itinerary(client, conn, monkeypatch)
    assert pin(client, auth(client, "binh@example.com"), tid, pid).status_code == 404


def test_replan_keeps_pinned_place(client, conn, monkeypatch):
    h, tid, pid = trip_with_itinerary(client, conn, monkeypatch)
    pin(client, h, tid, pid)
    other = add_place(conn, name="Hồ", vec=1)
    use_llm(monkeypatch, [reply(("search_places", {"query": "hồ"})),
                          reply(("submit_itinerary", {"summary": "không ghim", "days": [{"stops": [
                              {"place_id": other, "start_time": "09:00", "duration_min": 60}]}]})),
                          reply(("submit_itinerary", {"summary": "có ghim", "days": [{"stops": [
                              {"place_id": pid, "start_time": "09:00", "duration_min": 60},
                              {"place_id": other, "start_time": "11:00", "duration_min": 60}]}]}))])
    evs = events(client.post(f"/trips/{tid}/replan", headers=h,
                             json={"changes": {"budget": 3_000_000}, "message": "3 triệu"}))
    assert evs[-1]["type"] == "itinerary" and evs[-1]["itinerary"]["summary"] == "có ghim"
    got = client.get(f"/trips/{tid}", headers=h).json()
    assert got["itinerary"]["days"][0]["stops"][0]["pinned"] is True

import json
from contextlib import nullcontext

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from app import forecast, llm, trips
from app.db import get_conn
from app.main import app
from tests.fakes import FakeClient, reply
from tests.helpers import add_place, unit_vec


@pytest.fixture
def client(conn, monkeypatch):
    app.dependency_overrides[get_conn] = lambda: conn
    monkeypatch.setattr(trips, "stream_conn", lambda: nullcontext(conn))
    monkeypatch.setattr(llm, "embed", lambda texts: [unit_vec(0) for _ in texts])
    monkeypatch.setattr(forecast, "get_rain_chance", lambda *a, **k: None)
    yield TestClient(app)
    app.dependency_overrides.clear()


def auth(client, email="an@example.com"):
    token = client.post("/auth/register", json={"email": email, "password": "matkhau123"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def use_llm(monkeypatch, responses):
    monkeypatch.setattr(llm, "chat_client", lambda: FakeClient(responses))


def happy(pid):
    return [reply(("record_trip", {"destination": "da-lat", "days": 1, "budget": 2_000_000})),
            reply(("search_places", {"query": "cafe"})),
            reply(("submit_itinerary", {"summary": "ok", "days": [{"stops": [
                {"place_id": pid, "start_time": "09:00", "duration_min": 60, "reason": "cafe-chill"}]}]}))]


def test_create_trip_streams_and_persists(client, conn, monkeypatch):
    pid = add_place(conn, name="Cà phê Tùng", kind="cafe")
    use_llm(monkeypatch, happy(pid))
    h = auth(client)
    evs = events(client.post("/trips", json={"message": "Đà Lạt 1 ngày 2 triệu"}, headers=h))
    assert [e["type"] for e in evs] == ["thinking", "trip", "tool_call", "itinerary"]
    trip_id = evs[-1]["trip_id"]
    got = client.get(f"/trips/{trip_id}", headers=h).json()
    assert got["version"] == 1
    assert got["itinerary"]["days"][0]["stops"][0]["place_id"] == pid
    assert got["places"][str(pid)]["name"] == "Cà phê Tùng"
    assert [t["id"] for t in client.get("/trips", headers=h).json()] == [trip_id]


def test_other_user_gets_404(client, conn, monkeypatch):
    pid = add_place(conn)
    use_llm(monkeypatch, happy(pid))
    evs = events(client.post("/trips", json={"message": "x"}, headers=auth(client)))
    other = auth(client, "binh@example.com")
    assert client.get(f"/trips/{evs[-1]['trip_id']}", headers=other).status_code == 404
    assert client.get("/trips", headers=other).json() == []


def test_unsupported_destination_is_error_event(client, conn, monkeypatch):
    add_place(conn)
    use_llm(monkeypatch, [reply(("record_trip", {"destination": "unsupported", "days": 3, "budget": 1}))])
    evs = events(client.post("/trips", json={"message": "Phú Quốc"}, headers=auth(client)))
    assert evs[-1]["type"] == "error" and "da-lat" in evs[-1]["message"]
    assert conn.execute("SELECT count(*) AS n FROM trips").fetchone()["n"] == 0


def test_llm_down_is_error_event(client, conn, monkeypatch):
    add_place(conn)
    use_llm(monkeypatch, [openai.APIConnectionError(request=httpx.Request("POST", "http://llm"))])
    evs = events(client.post("/trips", json={"message": "x"}, headers=auth(client)))
    assert evs[-1] == {"type": "error", "message": "Không kết nối được AI, kiểm tra mạng rồi thử lại nhé."}


def test_requires_login(client):
    assert client.post("/trips", json={"message": "x"}).status_code == 401

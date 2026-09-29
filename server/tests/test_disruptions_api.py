import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.agent import itinerary_event
from app.db import get_conn
from app.domain import Draft, Trip
from app.main import app
from app.places import get_places
from app.rules import build_itinerary
from app.trips import save_itinerary
from tests.helpers import add_place

TRIP = Trip(destination="da-lat", days=1, budget=5_000_000, travel_mode="grab", preferred_tags=["cafe-chill"])


@pytest.fixture
def client(conn):
    app.dependency_overrides[get_conn] = lambda: conn
    yield TestClient(app)
    app.dependency_overrides.clear()


def auth(client, email="an@example.com"):
    token = client.post("/auth/register", json={"email": email, "password": "matkhau123"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def seed(conn, client, pinned=False):
    """Trip 1 ngày: Cafe A 09:00 → Bảo tàng 11:00. Ứng viên: Cafe B (cùng embedding), Cafe C (xa hơn)."""
    h = auth(client)
    uid = conn.execute("SELECT id FROM users").fetchone()["id"]
    cafe = add_place(conn, name="Cafe A", kind="cafe", tags=["cafe-chill"], vec=1)
    museum = add_place(conn, name="Bảo tàng", kind="tham-quan", tags=["lich-su"], vec=2)
    add_place(conn, name="Cafe B", kind="cafe", tags=["cafe-chill"], vec=1)
    add_place(conn, name="Cafe C", kind="cafe", tags=["check-in"], vec=3)
    tid = conn.execute("INSERT INTO trips(user_id, spec) VALUES (%s, %s) RETURNING id",
                       (uid, Jsonb(TRIP.model_dump(mode="json")))).fetchone()["id"]
    places = get_places(conn, [cafe, museum])
    draft = Draft.model_validate({"summary": "", "days": [{"stops": [
        {"place_id": cafe, "start_time": "09:00", "duration_min": 60, "pinned": pinned},
        {"place_id": museum, "start_time": "11:00", "duration_min": 60}]}]})
    ev = itinerary_event(build_itinerary(TRIP, draft, places), places)
    save_itinerary(conn, tid, ev["itinerary"], ev["places"])
    return h, tid


def disrupt(client, h, tid, version=1, stop=0, kind="closed"):
    return client.post(f"/trips/{tid}/disruptions", headers=h,
                       json={"version": version, "kind": kind, "day_index": 0, "stop_index": stop})


def first_stop_name(opt):
    return opt["places"][str(opt["itinerary"]["days"][0]["stops"][0]["place_id"])]["name"]


def test_closed_returns_options_and_logs(client, conn):
    h, tid = seed(conn, client)
    r = disrupt(client, h, tid)
    assert r.status_code == 200
    body = r.json()
    assert [first_stop_name(o) for o in body["options"]] == ["Cafe B", "Cafe C"]
    assert body["options"][0]["reason_codes"][0] == "INTENT_MATCH"
    row = conn.execute("SELECT base_version, disruption, chosen_index FROM proposals WHERE id = %s",
                       (body["proposal_id"],)).fetchone()
    assert (row["base_version"], row["disruption"]["kind"], row["chosen_index"]) == (1, "closed", None)


def test_apply_is_idempotent(client, conn):
    h, tid = seed(conn, client)
    pid = disrupt(client, h, tid).json()["proposal_id"]
    first = client.post(f"/trips/{tid}/proposals/{pid}/apply", headers=h, json={"option": 0}).json()
    again = client.post(f"/trips/{tid}/proposals/{pid}/apply", headers=h, json={"option": 0}).json()
    assert first["version"] == again["version"] == 2
    assert first["type"] == "itinerary" and first_stop_name(first) == "Cafe B"
    assert conn.execute("SELECT COUNT(*) AS n FROM itineraries WHERE trip_id = %s", (tid,)).fetchone()["n"] == 2
    assert conn.execute("SELECT chosen_index FROM proposals WHERE id = %s", (pid,)).fetchone()["chosen_index"] == 0


def test_apply_other_option_after_applied_409(client, conn):
    h, tid = seed(conn, client)
    pid = disrupt(client, h, tid).json()["proposal_id"]
    client.post(f"/trips/{tid}/proposals/{pid}/apply", headers=h, json={"option": 0})
    assert client.post(f"/trips/{tid}/proposals/{pid}/apply", headers=h, json={"option": 1}).status_code == 409


def test_stale_version_409(client, conn):
    h, tid = seed(conn, client)
    old = disrupt(client, h, tid).json()["proposal_id"]
    pid = disrupt(client, h, tid).json()["proposal_id"]
    client.post(f"/trips/{tid}/proposals/{pid}/apply", headers=h, json={"option": 0})  # → version 2
    assert disrupt(client, h, tid, version=1).status_code == 409
    assert client.post(f"/trips/{tid}/proposals/{old}/apply", headers=h, json={"option": 0}).status_code == 409


def test_other_user_404(client, conn):
    h, tid = seed(conn, client)
    pid = disrupt(client, h, tid).json()["proposal_id"]
    other = auth(client, "binh@example.com")
    assert disrupt(client, other, tid).status_code == 404
    assert client.post(f"/trips/{tid}/proposals/{pid}/apply", headers=other, json={"option": 0}).status_code == 404


def test_pinned_or_bad_stop_422(client, conn):
    h, tid = seed(conn, client, pinned=True)
    assert disrupt(client, h, tid).status_code == 422
    assert disrupt(client, h, tid, stop=9).status_code == 422


def test_no_feasible_when_no_same_kind_place(client, conn):
    h, tid = seed(conn, client)
    body = disrupt(client, h, tid, stop=1).json()  # Bảo tàng: không có tham-quan nào khác
    assert body["no_feasible"] == ["NO_CANDIDATE"]
    assert "options" not in body

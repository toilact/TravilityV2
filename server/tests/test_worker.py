import json
import threading
import time

import pytest

from app import forecast, jobs, llm, rules, trips, worker
from app.db import connect
from tests.conftest import TEST_URL
from tests.fakes import FakeClient, reply
from tests.helpers import add_place, unit_vec

RECORD = reply(("record_trip", {"destination": "da-lat", "days": 1, "budget": 2_000_000, "travel_mode": "grab"}))


@pytest.fixture(autouse=True)
def env(conn, rds, monkeypatch):
    monkeypatch.setattr(rules, "MEALS", ())
    monkeypatch.setattr(llm, "embed", lambda texts: [unit_vec(0) for _ in texts])
    monkeypatch.setattr(forecast, "get_rain_chance", lambda *a, **k: None)
    worker.ensure_group(rds)


def use_llm(monkeypatch, responses):
    monkeypatch.setattr(llm, "chat_client", lambda: FakeClient(responses))


def happy(pid):
    return [RECORD, reply(("search_places", {"query": "cafe"})),
            reply(("submit_itinerary", {"summary": "ok", "days": [{"stops": [
                {"place_id": pid, "start_time": "09:00", "duration_min": 60, "reason": "cafe-chill"}]}]}))]


def submit(conn):
    uid = conn.execute("INSERT INTO users(email, password_hash) VALUES ('an@example.com', 'x') RETURNING id"
                       ).fetchone()["id"]
    return jobs.enqueue("message", uid, {"message": "Đà Lạt 1 ngày 2 triệu", "trip_id": None})


def published(rds, job_id):
    return ["end" if "end" in f else json.loads(f["data"][6:]) for _, f in rds.xrange(f"events:{job_id}")]


def types(rds, job_id):
    return [e if e == "end" else e["type"] for e in published(rds, job_id)]


def count(conn, table):
    return conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]


def pending(rds):
    return rds.xpending_range("jobs", "planners", "-", "+", 10)


def test_job_runs_and_publishes_events_then_end(conn, rds, monkeypatch):
    use_llm(monkeypatch, happy(add_place(conn, kind="cafe")))
    job_id = submit(conn)
    assert worker.step(conn, rds, "w1") is True
    assert types(rds, job_id) == ["thinking", "trip", "tool_call", "itinerary", "end"]
    assert rds.get(f"job:{job_id}:done") == "1" and pending(rds) == []
    assert count(conn, "itineraries") == 1


def test_step_without_work_returns_false(conn, rds):
    assert worker.step(conn, rds, "w1") is False


def test_last_event_is_published_only_after_commit(conn, rds, monkeypatch):
    use_llm(monkeypatch, happy(add_place(conn, kind="cafe")))
    other, seen, real = connect(TEST_URL), [], jobs.publish

    def spy(job_id, data):
        seen.append((json.loads(data[6:])["type"], count(other, "trips")))
        real(job_id, data)

    monkeypatch.setattr(jobs, "publish", spy)
    submit(conn)
    worker.step(conn, rds, "w1")
    other.close()
    assert seen == [("thinking", 0), ("trip", 0), ("tool_call", 0), ("itinerary", 1)]


def test_error_event_still_commits_the_unfinished_trip(conn, rds, monkeypatch):
    add_place(conn)
    use_llm(monkeypatch, [RECORD, RuntimeError("boom")])
    job_id = submit(conn)
    worker.step(conn, rds, "w1")
    assert types(rds, job_id) == ["thinking", "trip", "error", "end"]
    assert count(conn, "trips") == 1 and pending(rds) == []  # Trip dở vẫn còn để User gửi tiếp, như chế độ một tiến trình


def test_done_job_is_not_run_again(conn, rds, monkeypatch):
    use_llm(monkeypatch, [])  # gọi LLM là hỏng
    job_id = submit(conn)
    rds.set(f"job:{job_id}:done", 1)
    worker.step(conn, rds, "w1")
    assert count(conn, "trips") == 0 and pending(rds) == [] and types(rds, job_id) == ["end"]

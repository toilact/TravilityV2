import json
import threading
import time

import pytest
from redis.exceptions import RedisError

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

    def spy_last(job_id, last):
        seen.append((json.loads(last[6:])["type"], count(other, "trips")))
        real_complete(job_id, last)

    real_complete = jobs.complete
    monkeypatch.setattr(jobs, "publish", spy)
    monkeypatch.setattr(jobs, "complete", spy_last)
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
    assert count(conn, "trips") == 0 and pending(rds) == [] and types(rds, job_id) == []


class Crash(BaseException):
    """Worker bị giết giữa chừng: guarded chỉ bắt Exception nên lỗi này xuyên qua như tiến trình chết."""


def crash_midway(conn, rds, monkeypatch):
    """w1 nhận việc, ghi Trip rồi chết trước khi có Itinerary. Trả (job_id, hàm plan thật, id Place)."""
    real, pid = trips.plan, add_place(conn, kind="cafe")

    def dying_plan(*a, **k):
        raise Crash()
        yield

    use_llm(monkeypatch, [RECORD])
    monkeypatch.setattr(trips, "plan", dying_plan)
    job_id = submit(conn)
    with pytest.raises(Crash):
        worker.step(conn, rds, "w1")
    return job_id, real, pid


def make_idle(rds, ms=30_000):
    """Giả lập việc đã im lặng ms mili giây (không tăng số lần giao)."""
    [p] = pending(rds)
    rds.xclaim("jobs", "planners", p["consumer"], 0, [p["message_id"]], idle=ms, justid=True)


def test_abandoned_job_is_rerun_without_duplicates(conn, rds, monkeypatch):
    job_id, real_plan, pid = crash_midway(conn, rds, monkeypatch)
    assert count(conn, "trips") == 0  # transaction của lần chạy dở đã rollback
    make_idle(rds)
    monkeypatch.setattr(trips, "plan", real_plan)
    use_llm(monkeypatch, happy(pid))
    assert worker.step(conn, rds, "w2") is True
    evs = published(rds, job_id)
    assert types(rds, job_id) == ["thinking", "thinking", "thinking", "trip", "tool_call", "itinerary", "end"]
    assert evs[1]["text"] == "Đang thử lại…"
    assert count(conn, "trips") == 1 and count(conn, "messages WHERE role = 'user'") == 1
    assert pending(rds) == []


def test_fresh_pending_job_is_not_stolen(conn, rds, monkeypatch):
    crash_midway(conn, rds, monkeypatch)  # vừa giao cho w1, chưa im lặng đủ 20 giây
    assert worker.step(conn, rds, "w2") is False
    assert pending(rds)[0]["consumer"] == "w1"


def test_third_delivery_gives_error_instead_of_running(conn, rds, monkeypatch):
    job_id, *_ = crash_midway(conn, rds, monkeypatch)
    make_idle(rds)
    with pytest.raises(Crash):
        worker.step(conn, rds, "w2")  # lần chạy lại cũng chết
    make_idle(rds)
    worker.step(conn, rds, "w3")
    assert published(rds, job_id)[-2:] == [
        {"type": "error", "message": "Có lỗi khi lập lịch trình, bạn thử lại nhé."}, "end"]
    assert pending(rds) == [] and count(conn, "trips") == 0


def test_heartbeat_keeps_job_fresh_without_counting_as_delivery(conn, rds, monkeypatch):
    crash_midway(conn, rds, monkeypatch)
    make_idle(rds)
    monkeypatch.setattr(worker, "BEAT_S", 0.01)
    stop = threading.Event()
    t = threading.Thread(target=worker._beat, args=(rds, pending(rds)[0]["message_id"], "w1", stop))
    t.start()
    time.sleep(0.1)
    stop.set()
    t.join()
    [p] = pending(rds)
    assert p["time_since_delivered"] < 5000 and p["times_delivered"] == 1


def test_job_runs_under_heartbeat_and_stops_it(conn, rds, monkeypatch):
    beats = []
    monkeypatch.setattr(worker, "_beat", lambda c, msg_id, me, stop: beats.append((msg_id, me, stop)))
    use_llm(monkeypatch, happy(add_place(conn, kind="cafe")))
    submit(conn)
    [(msg_id, _)] = rds.xrange("jobs")
    worker.step(conn, rds, "w1")
    time.sleep(0.05)
    assert len(beats) == 1 and beats[0][:2] == (msg_id, "w1") and beats[0][2].is_set()


def test_heartbeat_stops_when_job_crashes(conn, rds, monkeypatch):
    beats = []
    monkeypatch.setattr(worker, "_beat", lambda c, msg_id, me, stop: beats.append(stop))
    crash_midway(conn, rds, monkeypatch)
    time.sleep(0.05)
    assert beats[0].is_set()


def test_completion_is_one_atomic_write(rds):
    jobs.publish("j1", "data: a\n\n")
    jobs.complete("j1", "data: z\n\n")
    assert [f for _, f in rds.xrange("events:j1")] == [{"data": "data: a\n\n"}, {"data": "data: z\n\n"}, {"end": "1"}]
    assert rds.get("job:j1:done") == "1" and 0 < rds.ttl("job:j1:done") <= 3600


def test_failed_completion_leaves_job_not_done(conn, rds, monkeypatch):
    """Redis hỏng đúng lúc hoàn tất: không được có cờ done mà thiếu event cuối (client sẽ không bao giờ thấy lịch)."""
    def broken(job_id, last):
        raise RedisError("mất kết nối")

    use_llm(monkeypatch, happy(add_place(conn, kind="cafe")))
    monkeypatch.setattr(jobs, "complete", broken)
    job_id = submit(conn)
    with pytest.raises(RedisError):
        worker.step(conn, rds, "w1")
    assert rds.get(f"job:{job_id}:done") is None and len(pending(rds)) == 1


def test_job_that_waited_longer_than_the_api_is_dropped(conn, rds, monkeypatch):
    """api đã báo lỗi cho client sau QUIET_S im lặng; chạy việc đó muộn sẽ sinh Trip mà User không biết."""
    use_llm(monkeypatch, happy(add_place(conn, kind="cafe")))
    uid = conn.execute("INSERT INTO users(email, password_hash) VALUES ('an@example.com', 'x') RETURNING id"
                       ).fetchone()["id"]
    old_id = f"{int((time.time() - jobs.QUIET_S - 5) * 1000)}-0"
    rds.xadd("jobs", {"job_id": "cu", "kind": "message", "user_id": uid,
                      "params": json.dumps({"message": "Đà Lạt 1 ngày 2 triệu", "trip_id": None})}, id=old_id)
    assert worker.step(conn, rds, "w1") is True
    assert count(conn, "trips") == 0 and pending(rds) == []
    assert types(rds, "cu") == ["error", "end"]


def test_live_long_job_is_not_stolen(conn, rds, monkeypatch):
    """Việc chạy lâu hơn ngưỡng nhận lại: nhịp tim giữ nó khỏi bị worker khác giành."""
    pid, real_plan = add_place(conn, kind="cafe"), trips.plan

    def slow_plan(*a, **k):
        time.sleep(0.8)
        yield from real_plan(*a, **k)

    monkeypatch.setattr(trips, "plan", slow_plan)
    monkeypatch.setattr(worker, "CLAIM_IDLE_MS", 200)
    monkeypatch.setattr(worker, "BEAT_S", 0.05)
    use_llm(monkeypatch, happy(pid))
    job_id = submit(conn)
    w1_conn = connect(TEST_URL)
    t = threading.Thread(target=worker.step, args=(w1_conn, rds, "w1"))
    t.start()
    time.sleep(0.5)  # quá 200 ms: không có nhịp tim thì w2 sẽ giành việc
    assert worker.step(conn, rds, "w2") is False
    t.join()
    w1_conn.close()
    assert types(rds, job_id) == ["thinking", "trip", "tool_call", "itinerary", "end"] and count(conn, "trips") == 1

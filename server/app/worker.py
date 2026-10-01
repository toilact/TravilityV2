"""planner: nhận việc lập lịch từ Redis Streams và chạy đúng các generator của app.trips (spec scale §5).

Chạy: python -m app.worker
"""
import json
import logging

from redis.exceptions import ResponseError

from app import jobs, trips

logger = logging.getLogger(__name__)


def ensure_group(c) -> None:
    try:
        c.xgroup_create(jobs.STREAM, jobs.GROUP, id="0", mkstream=True)
    except ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def run_job(conn, c, me: str, msg_id: str, f: dict, retry: bool = False) -> None:
    """Chạy một việc trong một transaction: worker chết giữa chừng → Postgres rollback, lần chạy lại bắt đầu sạch.

    Event cuối chỉ phát sau khi commit, để client không bao giờ thấy Itinerary chưa được lưu.
    """
    job_id = f["job_id"]
    if c.exists(f"job:{job_id}:done"):  # đã xong ở lần giao trước
        jobs.finish(job_id)
        c.xack(jobs.STREAM, jobs.GROUP, msg_id)
        return
    held = None
    with conn.transaction():
        for ev in trips.guarded(trips.JOBS[f["kind"]](conn, int(f["user_id"]), **json.loads(f["params"]))):
            if held is not None:
                jobs.publish(job_id, held)
            held = ev
    c.set(f"job:{job_id}:done", 1, ex=jobs.TTL_S)
    if held is not None:
        jobs.publish(job_id, held)
    jobs.finish(job_id)
    c.xack(jobs.STREAM, jobs.GROUP, msg_id)
    logger.info("xong việc %s (%s)", job_id, f["kind"])


def step(conn, c, me: str) -> bool:
    """Nhận và chạy tối đa một việc; True nếu có việc.

    ponytail: một việc một lúc mỗi tiến trình; cần chạy song song nhiều hơn thì tăng số bản planner.
    """
    got = c.xreadgroup(jobs.GROUP, me, {jobs.STREAM: ">"}, count=1, block=500)
    if not got:
        return False
    msg_id, f = got[0][1][0]
    run_job(conn, c, me, msg_id, f)
    return True

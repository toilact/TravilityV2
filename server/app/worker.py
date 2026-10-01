"""planner: nhận việc lập lịch từ Redis Streams và chạy đúng các generator của app.trips (spec scale §5).

Chạy: python -m app.worker
"""
import json
import logging
import socket
import threading
import time

from redis.exceptions import RedisError, ResponseError

from app import jobs, kv, trips
from app.db import apply_schema, connect

logger = logging.getLogger(__name__)
CLAIM_IDLE_MS = 20_000  # việc im lặng quá bấy nhiêu = worker giữ nó đã chết → worker khác nhận lại
BEAT_S = 5  # worker đang chạy việc báo "còn sống" mỗi bấy nhiêu giây
MAX_DELIVERIES = 2  # chạy lại tối đa 1 lần (spec §5.2)


def _beat(c, msg_id: str, me: str, stop: threading.Event) -> None:
    """Nhịp tim: XCLAIM JUSTID đặt lại thời gian im lặng của việc mà không tăng số lần giao."""
    while not stop.wait(BEAT_S):
        try:
            c.xclaim(jobs.STREAM, jobs.GROUP, me, 0, [msg_id], justid=True)
        except RedisError:
            pass


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

    def close():
        jobs.finish(job_id)
        c.xack(jobs.STREAM, jobs.GROUP, msg_id)

    if c.exists(f"job:{job_id}:done"):  # đã xong ở lần giao trước
        return close()
    if retry:
        delivered = c.xpending_range(jobs.STREAM, jobs.GROUP, msg_id, msg_id, 1)[0]["times_delivered"]
        if delivered > MAX_DELIVERIES:
            jobs.publish(job_id, trips.sse({"type": "error", "message": "Có lỗi khi lập lịch trình, bạn thử lại nhé."}))
            return close()
        jobs.publish(job_id, trips.sse({"type": "thinking", "text": "Đang thử lại…"}))
    stop = threading.Event()
    threading.Thread(target=_beat, args=(c, msg_id, me, stop), daemon=True).start()
    try:
        held = None
        with conn.transaction():
            for ev in trips.guarded(trips.JOBS[f["kind"]](conn, int(f["user_id"]), **json.loads(f["params"]))):
                if held is not None:
                    jobs.publish(job_id, held)
                held = ev
        c.set(f"job:{job_id}:done", 1, ex=jobs.TTL_S)
        if held is not None:
            jobs.publish(job_id, held)
        close()
        logger.info("xong việc %s (%s)", job_id, f["kind"])
    finally:
        stop.set()


def step(conn, c, me: str) -> bool:
    """Nhận và chạy tối đa một việc; True nếu có việc. Việc bị worker chết bỏ dở được ưu tiên trước.

    ponytail: một việc một lúc mỗi tiến trình; cần chạy song song nhiều hơn thì tăng số bản planner.
    """
    claimed = c.xautoclaim(jobs.STREAM, jobs.GROUP, me, CLAIM_IDLE_MS, count=1)[1]
    if claimed:
        run_job(conn, c, me, *claimed[0], retry=True)
        return True
    got = c.xreadgroup(jobs.GROUP, me, {jobs.STREAM: ">"}, count=1, block=500)
    if not got:
        return False
    run_job(conn, c, me, *got[0][1][0])
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    c, me = kv.client(), socket.gethostname()
    if c is None:
        raise SystemExit("planner cần REDIS_URL")
    with connect() as conn:
        apply_schema(conn)
    logger.info("planner %s sẵn sàng", me)
    conn = None
    while True:
        try:
            ensure_group(c)  # mỗi vòng: `redis-cli flushdb` trong runbook xoá luôn consumer group
            conn = conn or connect()
            step(conn, c, me)
        except Exception:
            logger.exception("planner lỗi, thử lại sau 1 giây")
            if conn is not None:
                conn.close()
            conn = None
            time.sleep(1)


if __name__ == "__main__":
    main()

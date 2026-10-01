"""Queue lập lịch trên Redis Streams, phía api: giới hạn theo User, đẩy việc, chuyển event về client (spec scale §5).

Phía worker ở app/worker.py.
"""
import math
import time

from fastapi import HTTPException
from redis.exceptions import RedisError

from app import kv
from app.config import settings

_now = time.time  # test thay bằng đồng hồ giả


def check_rate(user_id: int) -> None:
    """Mỗi User tối đa PLAN_RPM việc mỗi phút (cửa sổ cố định). Redis lỗi → cho qua (spec §5.3)."""
    c = kv.client()
    if c is None or not settings.plan_rpm:
        return
    now = _now()
    key = f"rl:{user_id}:{int(now // 60)}"
    try:
        n = c.incr(key)
        if n == 1:
            c.expire(key, 120)
        if n <= settings.plan_rpm:
            return
        c.incr("rl:blocked")
    except RedisError:
        return
    wait = max(1, math.ceil(60 - now % 60))
    raise HTTPException(429, f"Bạn gửi yêu cầu quá nhanh, chờ {wait} giây rồi thử lại nhé.",
                        headers={"Retry-After": str(wait)})

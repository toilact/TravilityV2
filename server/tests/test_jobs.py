import json
import threading

import pytest
from fastapi import HTTPException

from app import jobs, kv
from app.config import settings


@pytest.fixture
def minute(monkeypatch):
    """Đồng hồ đứng ở giây thứ 10 của một phút; test tự tua bằng minute[0] += …"""
    t = [60_000_010.0]
    monkeypatch.setattr(jobs, "_now", lambda: t[0])
    return t


@pytest.fixture
def redis_down(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "redis://localhost:1/0")
    monkeypatch.setattr(kv, "_client", None)


def test_sixth_request_in_a_minute_is_429(rds, minute):
    for _ in range(5):
        jobs.check_rate(7)
    with pytest.raises(HTTPException) as e:
        jobs.check_rate(7)
    assert e.value.status_code == 429
    assert e.value.headers["Retry-After"] == "50" and "50 giây" in e.value.detail
    assert rds.get("rl:blocked") == "1"


def test_other_user_and_next_minute_are_not_limited(rds, minute):
    for _ in range(5):
        jobs.check_rate(7)
    jobs.check_rate(8)
    minute[0] += 60
    jobs.check_rate(7)


def test_counter_expires(rds, minute):
    jobs.check_rate(7)
    assert 0 < rds.ttl("rl:7:1000000") <= 120


def test_plan_rpm_zero_means_no_limit(rds, minute, monkeypatch):
    monkeypatch.setattr(settings, "plan_rpm", 0)
    for _ in range(20):
        jobs.check_rate(7)
    assert rds.keys("rl:*") == []


def test_rate_limit_lets_through_when_redis_down(redis_down):
    for _ in range(10):
        jobs.check_rate(7)


def test_no_redis_url_means_no_limit():
    for _ in range(10):
        jobs.check_rate(7)

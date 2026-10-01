import os

import pytest

os.environ["GOONG_API_KEY"] = ""  # máy dev có key trong .env — test không được gọi Goong thật
os.environ["REDIS_URL"] = ""  # test không đụng Redis, trừ khi xin fixture rds
os.environ["DEMO_TODAY"] = ""

from app import distance, kv
from app.config import settings
from app.db import apply_schema, connect

TEST_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://travility:travility@localhost:5432/travility_test"
)
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")


@pytest.fixture
def conn():
    c = connect(TEST_URL)
    c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    apply_schema(c)
    yield c
    c.close()


@pytest.fixture
def rds(monkeypatch):
    """Redis thật (DB 15) đã xoá sạch; settings.redis_url trỏ vào đó trong lúc test chạy."""
    monkeypatch.setattr(settings, "redis_url", TEST_REDIS_URL)
    monkeypatch.setattr(kv, "_client", None)
    c = kv.client()
    c.flushdb()
    yield c
    c.flushdb()


@pytest.fixture(autouse=True)
def _clean_distance():
    distance._cache.clear()
    distance._down_until = 0.0

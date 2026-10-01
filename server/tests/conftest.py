import os

import pytest

os.environ["GOONG_API_KEY"] = ""  # máy dev có key trong .env — test không được gọi Goong thật

from app import distance
from app.db import apply_schema, connect

TEST_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://travility:travility@localhost:5432/travility_test"
)


@pytest.fixture
def conn():
    c = connect(TEST_URL)
    c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    apply_schema(c)
    yield c
    c.close()


@pytest.fixture(autouse=True)
def _clean_distance():
    distance._cache.clear()
    distance._down_until = 0.0

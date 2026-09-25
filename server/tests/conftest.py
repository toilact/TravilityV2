import os

import pytest

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

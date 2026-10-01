import threading

from app.db import apply_schema, connect
from tests.conftest import TEST_URL


def test_apply_schema_survives_concurrent_startup(conn):
    """2 bản api + 2 planner cùng khởi động trên database trống."""
    conns = [connect(TEST_URL) for _ in range(4)]
    conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    errors, gate = [], threading.Barrier(4, timeout=10)

    def boot(c):
        try:
            gate.wait()
            apply_schema(c)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=boot, args=(c,)) for c in conns]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for c in conns:
        c.close()
    assert errors == []
    assert conn.execute("SELECT count(*) AS n FROM users").fetchone()["n"] == 0

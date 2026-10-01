from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from app.config import settings

SCHEMA = Path(__file__).with_name("schema.sql")


def connect(url: str | None = None) -> psycopg.Connection:
    conn = psycopg.connect(url or settings.database_url, row_factory=dict_row, autocommit=True)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn


def apply_schema(conn: psycopg.Connection) -> None:
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(4949)")  # các bản api và planner trong cụm khởi động cùng lúc
        conn.execute(SCHEMA.read_text())
    register_vector(conn)  # extension có thể vừa được tạo lại → đăng ký lại kiểu vector


def get_conn():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()

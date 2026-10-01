import logging
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from app.config import settings

logger = logging.getLogger(__name__)
SCHEMA = Path(__file__).with_name("schema.sql")
CONNECT_TIMEOUT_S = 2  # node chết phải lộ ra nhanh để còn chuyển sang node khác (spec scale §10)


def _open(url: str) -> psycopg.Connection:
    return psycopg.connect(url, row_factory=dict_row, autocommit=True, connect_timeout=CONNECT_TIMEOUT_S)


def connect(url: str | None = None) -> psycopg.Connection:
    """Kết nối node chính của database chung (ghi được, có kiểu vector)."""
    conn = _open(url or settings.database_url)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn


def catalog_read() -> psycopg.Connection:
    """Kết nối chỉ để đọc Place / Destination: bản sao nếu có CATALOG_REPLICA_URL, bản sao chết → node chính (spec §8)."""
    if settings.catalog_replica_url:
        try:
            conn = _open(settings.catalog_replica_url)
        except psycopg.OperationalError:
            logger.warning("bản sao pg-catalog không kết nối được, đọc node chính")
        else:
            register_vector(conn)  # bản sao là hot standby: không CREATE EXTENSION ở đây
            return conn
    return connect()


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

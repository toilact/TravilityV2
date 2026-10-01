"""Một cửa cho mọi lần đọc Place / Destination (spec scale §8): code gọi không biết dữ liệu đến từ đâu.

`conn` là kết nối Trip của người gọi. Nó chỉ được dùng để đọc Place ở chế độ đơn giản (một database);
có CATALOG_REPLICA_URL hoặc SHARD_URLS thì module tự mở kết nối đọc database chung.
"""
from contextlib import contextmanager

from app import db, places
from app.config import settings
from app.domain import Place


@contextmanager
def _reader(conn):
    if settings.catalog_replica_url or settings.shard_urls:
        with db.catalog_read() as c:
            yield c
    else:
        yield conn


def search_places(conn, destination: str, query: str, embed_fn, kind: str | None = None,
                  must_have_tags=(), exclude_tags=(), limit: int = 8) -> list[Place]:
    vec = embed_fn([query])[0]
    with _reader(conn) as c:
        return places.search_places(c, destination, vec, kind, must_have_tags, exclude_tags, limit)


def similar_places(conn, place_id: int, kind: str, exclude_ids=(), exclude_tags=(), limit: int = 20) -> list[Place]:
    with _reader(conn) as c:
        return places.similar_places(c, place_id, kind, exclude_ids, exclude_tags, limit)


def get_places(conn, ids) -> dict[int, Place]:
    with _reader(conn) as c:
        return places.get_places(c, list(ids))


def list_destinations(conn) -> list[dict]:
    with _reader(conn) as c:
        return places.list_destinations(c)

"""Service places: tìm Place bằng vector, Place tương tự, Place theo id, Destination (spec scale §8).

Chạy: uvicorn app.places_service:app. Đọc bản sao của database chung; bản sao chết thì đọc node chính.
Chỉ nghe trong mạng nội bộ của cụm nên không kiểm JWT. Không được đặt PLACES_URL cho service này.
"""
from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel

from app import db, llm, places
from app.domain import Place

app = FastAPI(title="Travility places")


def get_read():
    conn = db.catalog_read()
    try:
        yield conn
    finally:
        conn.close()


class SearchIn(BaseModel):
    destination: str
    query: str
    kind: str | None = None
    must_have_tags: list[str] = []
    exclude_tags: list[str] = []
    limit: int = 8


class SimilarIn(BaseModel):
    place_id: int
    kind: str
    exclude_ids: list[int] = []
    exclude_tags: list[str] = []
    limit: int = 20


@app.post("/search")
def search(body: SearchIn, conn=Depends(get_read)) -> list[Place]:
    vec = llm.embed([body.query])[0]
    return places.search_places(conn, body.destination, vec, body.kind, body.must_have_tags, body.exclude_tags,
                                body.limit)


@app.post("/similar")
def similar(body: SimilarIn, conn=Depends(get_read)) -> list[Place]:
    return places.similar_places(conn, body.place_id, body.kind, body.exclude_ids, body.exclude_tags, body.limit)


@app.get("/places")
def by_ids(ids: list[int] = Query(default=[]), conn=Depends(get_read)) -> list[Place]:
    return list(places.get_places(conn, ids).values())


@app.get("/destinations")
def destinations(conn=Depends(get_read)) -> list[dict]:
    return places.list_destinations(conn)


@app.get("/health")
def health():
    return {"ok": True}

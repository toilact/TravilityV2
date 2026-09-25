import datetime as dt
import json

import openai
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app import forecast, llm
from app.agent import TripParseError, UnsupportedDestination, parse_trip, plan
from app.auth import current_user
from app.config import settings
from app.db import connect, get_conn
from app.places import list_destinations

router = APIRouter()
stream_conn = connect  # SSE chạy sau khi handler trả về → tự mở kết nối riêng; test thay bằng kết nối test


class NewTrip(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("/destinations")
def destinations(conn=Depends(get_conn)):
    return list_destinations(conn)


@router.post("/trips")
def create_trip(body: NewTrip, user_id: int = Depends(current_user)):
    def events():
        with stream_conn() as conn:
            try:
                yield from _run(conn, user_id, body.message)
            except openai.OpenAIError:
                yield sse({"type": "error", "message": "Không kết nối được AI, kiểm tra mạng rồi thử lại nhé."})

    return StreamingResponse(events(), media_type="text/event-stream")


def _run(conn, user_id: int, message: str):
    dests = {d["slug"]: d for d in list_destinations(conn)}
    client = llm.chat_client()
    yield sse({"type": "thinking", "text": "Đang đọc yêu cầu của bạn…"})
    try:
        trip = parse_trip(client, settings.llm_model, message,
                          {slug: d["name"] for slug, d in dests.items()}, dt.date.today())
    except (UnsupportedDestination, TripParseError) as e:
        yield sse({"type": "error", "message": str(e)})
        return
    d = dests[trip.destination]
    trip_json = trip.model_dump(mode="json")
    trip_id = conn.execute("INSERT INTO trips(user_id, spec) VALUES (%s, %s) RETURNING id",
                           (user_id, Jsonb(trip_json))).fetchone()["id"]
    yield sse({"type": "trip", "trip_id": trip_id, "trip": trip_json, "center": [d["lon"], d["lat"]]})

    rain = forecast.get_rain_chance(d["lat"], d["lon"], trip.start_date, trip.days)
    for ev in plan(conn, client, settings.llm_model, trip, llm.embed, rain):
        if ev["type"] == "itinerary":
            conn.execute("INSERT INTO itineraries(trip_id, version, data) VALUES (%s, 1, %s)",
                         (trip_id, Jsonb({"itinerary": ev["itinerary"], "places": ev["places"]})))
            ev = {**ev, "trip_id": trip_id, "version": 1}
        yield sse(ev)


@router.get("/trips")
def list_trips(user_id: int = Depends(current_user), conn=Depends(get_conn)):
    return conn.execute("SELECT id, spec, created_at FROM trips WHERE user_id = %s ORDER BY id DESC",
                        (user_id,)).fetchall()


@router.get("/trips/{trip_id}")
def get_trip(trip_id: int, user_id: int = Depends(current_user), conn=Depends(get_conn)):
    trip = conn.execute("SELECT id, spec FROM trips WHERE id = %s AND user_id = %s",
                        (trip_id, user_id)).fetchone()
    if not trip:
        raise HTTPException(404, "Không tìm thấy chuyến đi")
    it = conn.execute("SELECT version, data FROM itineraries WHERE trip_id = %s ORDER BY version DESC LIMIT 1",
                      (trip_id,)).fetchone()
    return {"trip_id": trip["id"], "trip": trip["spec"],
            "version": it["version"] if it else None,
            "itinerary": it["data"]["itinerary"] if it else None,
            "places": it["data"]["places"] if it else {}}

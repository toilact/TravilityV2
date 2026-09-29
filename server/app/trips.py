import datetime as dt
import json
import logging
from zoneinfo import ZoneInfo

import openai
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, ValidationError

from app import forecast, llm
from app.agent import (TripParseError, UnsupportedDestination, apply_answers, merge_trip, missing_questions,
                       parse_trip, plan)
from app.domain import Hub, Trip, TripAnswers
from app.auth import current_user
from app.config import settings
from app.db import connect, get_conn
from app.places import list_destinations

logger = logging.getLogger(__name__)
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

router = APIRouter()
stream_conn = connect  # SSE chạy sau khi handler trả về → tự mở kết nối riêng; test thay bằng kết nối test


class NewTrip(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    trip_id: int | None = None  # có → tin nhắn tiếp theo của Trip đang mở (PRD §5.4: chat gắn với Trip)


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("/destinations")
def destinations(conn=Depends(get_conn)):
    return list_destinations(conn)


def _stream(run) -> StreamingResponse:
    """Chạy generator `run(conn)` trong SSE; lỗi → event error tiếng Việt."""
    def events():
        with stream_conn() as conn:
            try:
                yield from run(conn)
            except openai.OpenAIError:
                logger.exception("Lỗi gọi AI khi lập lịch trình")
                yield sse({"type": "error", "message": "Không kết nối được AI, kiểm tra mạng rồi thử lại nhé."})
            except Exception:
                logger.exception("Lỗi không lường trước khi lập lịch trình")
                yield sse({"type": "error", "message": "Có lỗi khi lập lịch trình, bạn thử lại nhé."})

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/trips")
def create_trip(body: NewTrip, user_id: int = Depends(current_user), conn=Depends(get_conn)):
    prev = None
    if body.trip_id is not None:
        prev = conn.execute("SELECT id, spec, user_messages FROM trips WHERE id = %s AND user_id = %s",
                            (body.trip_id, user_id)).fetchone()
        if not prev:
            raise HTTPException(404, "Không tìm thấy chuyến đi")
    return _stream(lambda c: _run(c, user_id, body.message, prev))


def _hub(dest: dict, trip: Trip) -> Hub | None:
    h = dest["hubs"].get(trip.arrival_mode) if trip.arrival_mode else None
    return Hub.model_validate(h) if h else None


def _trip_event(trip_id: int, trip: Trip, dest: dict) -> str:
    return sse({"type": "trip", "trip_id": trip_id, "trip": trip.model_dump(mode="json"),
                "center": [dest["lon"], dest["lat"]]})


def _plan_and_save(conn, client, trip_id: int, trip: Trip, dest: dict, user_messages: list[str]):
    rain = forecast.get_rain_chance(dest["lat"], dest["lon"], trip.start_date, trip.days)
    for ev in plan(conn, client, settings.llm_model, trip, llm.embed, rain, _hub(dest, trip), user_messages):
        if ev["type"] == "itinerary":
            version = conn.execute(
                """INSERT INTO itineraries(trip_id, version, data)
                   SELECT %s, COALESCE(MAX(version), 0) + 1, %s FROM itineraries WHERE trip_id = %s
                   RETURNING version""",
                (trip_id, Jsonb({"itinerary": ev["itinerary"], "places": ev["places"]}), trip_id)).fetchone()["version"]
            ev = {**ev, "trip_id": trip_id, "version": version}
        yield sse(ev)


def _parse_input(user_messages: list[str]) -> str:
    if len(user_messages) == 1:
        return user_messages[0]
    return "\n".join(f"Tin nhắn {i + 1}: {m}" for i, m in enumerate(user_messages))


def _run(conn, user_id: int, message: str, prev: dict | None = None):
    dests = {d["slug"]: d for d in list_destinations(conn)}
    client = llm.chat_client()
    user_messages = [*(prev["user_messages"] if prev else []), message]
    yield sse({"type": "thinking", "text": "Đang đọc yêu cầu của bạn…"})
    try:
        trip = parse_trip(client, settings.llm_model, _parse_input(user_messages),
                          {slug: d["name"] for slug, d in dests.items()},
                          dt.datetime.now(VN_TZ).date())
        if prev:  # tin nhắn tiếp theo: giữ câu trả lời cũ, không hỏi lại lần 2 (spec §3)
            trip = apply_answers(merge_trip(Trip.model_validate(prev["spec"]), trip), TripAnswers())
    except (UnsupportedDestination, TripParseError) as e:
        yield sse({"type": "error", "message": str(e)})
        return
    except ValidationError as e:
        yield sse({"type": "error", "message": e.errors()[0]["msg"].removeprefix("Value error, ")})
        return
    d = dests[trip.destination]
    spec = Jsonb(trip.model_dump(mode="json"))
    if prev:
        trip_id = prev["id"]
        conn.execute("UPDATE trips SET spec = %s, user_messages = %s WHERE id = %s", (spec, user_messages, trip_id))
    else:
        trip_id = conn.execute("INSERT INTO trips(user_id, spec, user_messages) VALUES (%s, %s, %s) RETURNING id",
                               (user_id, spec, user_messages)).fetchone()["id"]
    yield _trip_event(trip_id, trip, d)
    questions = [] if prev else missing_questions(trip)
    if questions:
        yield sse({"type": "clarify", "trip_id": trip_id, "questions": questions})
        return
    yield from _plan_and_save(conn, client, trip_id, trip, d, user_messages)


@router.post("/trips/{trip_id}/plan")
def plan_trip(trip_id: int, answers: TripAnswers, user_id: int = Depends(current_user), conn=Depends(get_conn)):
    row = conn.execute("SELECT spec, user_messages FROM trips WHERE id = %s AND user_id = %s",
                       (trip_id, user_id)).fetchone()
    if not row:
        raise HTTPException(404, "Không tìm thấy chuyến đi")
    if conn.execute("SELECT 1 FROM itineraries WHERE trip_id = %s", (trip_id,)).fetchone():
        raise HTTPException(409, "Chuyến đi đã có lịch trình")
    try:
        trip = apply_answers(Trip.model_validate(row["spec"]), answers)
    except ValidationError as e:
        raise HTTPException(422, e.errors()[0]["msg"].removeprefix("Value error, ")) from None
    conn.execute("UPDATE trips SET spec = %s WHERE id = %s", (Jsonb(trip.model_dump(mode="json")), trip_id))

    def run(c):
        dest = next(d for d in list_destinations(c) if d["slug"] == trip.destination)
        yield _trip_event(trip_id, trip, dest)
        yield from _plan_and_save(c, llm.chat_client(), trip_id, trip, dest, row["user_messages"])

    return _stream(run)


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

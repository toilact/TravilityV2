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
from app.domain import Hub, Itinerary, Trip, TripAnswers
from app.followup import changed_trip, followup
from app.auth import current_user
from app.config import settings
from app.db import connect, get_conn
from app.places import get_places, list_destinations

logger = logging.getLogger(__name__)
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

router = APIRouter()
stream_conn = connect  # SSE chạy sau khi handler trả về → tự mở kết nối riêng; test thay bằng kết nối test


def _today() -> dt.date:
    """Hôm nay theo giờ VN. DEMO_TODAY đóng băng ngày để bản ghi replay của llm-gateway trúng cache."""
    return settings.demo_today or dt.datetime.now(VN_TZ).date()


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
        prev = conn.execute("SELECT id, spec, user_messages, pending_replan FROM trips WHERE id = %s AND user_id = %s",
                            (body.trip_id, user_id)).fetchone()
        if not prev:
            raise HTTPException(404, "Không tìm thấy chuyến đi")
    return _stream(lambda c: _run(c, user_id, body.message, prev))


def hub_for(dest: dict, trip: Trip) -> Hub | None:
    h = dest["hubs"].get(trip.arrival_mode) if trip.arrival_mode else None
    return Hub.model_validate(h) if h else None


def _trip_event(trip_id: int, trip: Trip, dest: dict) -> str:
    return sse({"type": "trip", "trip_id": trip_id, "trip": trip.model_dump(mode="json"),
                "center": [dest["lon"], dest["lat"]]})


def save_itinerary(conn, trip_id: int, itinerary: dict, places: dict) -> int:
    """Lưu một version Itinerary mới (bất biến) và trả số version."""
    return conn.execute(
        """INSERT INTO itineraries(trip_id, version, data)
           SELECT %s, COALESCE(MAX(version), 0) + 1, %s FROM itineraries WHERE trip_id = %s
           RETURNING version""",
        (trip_id, Jsonb({"itinerary": itinerary, "places": places}), trip_id)).fetchone()["version"]


def log_message(conn, trip_id: int, role: str, text: str, version: int | None = None) -> None:
    conn.execute("INSERT INTO messages(trip_id, role, text, version) VALUES (%s, %s, %s, %s)",
                 (trip_id, role, text, version))


def _plan_and_save(conn, client, trip_id: int, trip: Trip, dest: dict, user_messages: list[str], previous=None):
    rain = forecast.get_rain_chance(dest["lat"], dest["lon"], trip.start_date, trip.days, today=_today())
    for ev in plan(conn, client, settings.llm_model, trip, llm.embed, rain, hub_for(dest, trip), user_messages,
                   previous):
        if ev["type"] == "itinerary":
            version = save_itinerary(conn, trip_id, ev["itinerary"], ev["places"])
            log_message(conn, trip_id, "ai", ev["itinerary"]["summary"], version)
            ev = {**ev, "trip_id": trip_id, "version": version}
        yield sse(ev)


def _parse_input(user_messages: list[str]) -> str:
    if len(user_messages) == 1:
        return user_messages[0]
    return "\n".join(f"Tin nhắn {i + 1}: {m}" for i, m in enumerate(user_messages))


def load_itinerary(conn, trip_id: int, version: int | None = None) -> tuple[int, Itinerary, dict] | None:
    """Đọc một version (mặc định bản mới nhất); stop.pinned lấy từ trips.pinned_place_ids, không từ data đã lưu."""
    row = conn.execute(
        """SELECT i.version, i.data, t.pinned_place_ids FROM itineraries i JOIN trips t ON t.id = i.trip_id
           WHERE i.trip_id = %s AND (%s::int IS NULL OR i.version = %s) ORDER BY i.version DESC LIMIT 1""",
        (trip_id, version, version)).fetchone()
    if not row:
        return None
    itin = Itinerary.model_validate(row["data"]["itinerary"])
    pins = set(row["pinned_place_ids"])
    for d in itin.days:
        for s in d.stops:
            s.pinned = s.place_id in pins
    return row["version"], itin, row["data"]["places"]


def latest_itinerary(conn, trip_id: int) -> tuple[int, Itinerary] | None:
    r = load_itinerary(conn, trip_id)
    return (r[0], r[1]) if r else None


def itinerary_places(conn, itin: Itinerary) -> dict:
    ids = {s.place_id for d in itin.days for s in d.stops} | ({itin.stay_place_id} - {None})
    return get_places(conn, list(ids))


def _follow_up(conn, client, prev: dict, itin: Itinerary, dest: dict, message: str):
    """Trip đã có lịch trình: trả lời / sửa, không lập lại từ đầu (#22)."""
    trip = Trip.model_validate(prev["spec"])
    rain = [d.rain_chance for d in itin.days]
    pending = prev["pending_replan"]
    conn.execute("UPDATE trips SET pending_replan = NULL WHERE id = %s", (prev["id"],))  # chỉ sống 1 lượt
    for ev in followup(conn, client, settings.llm_model, trip, itin, itinerary_places(conn, itin), message,
                       rain, hub_for(dest, trip), llm.embed, pending):
        if ev["type"] == "replan_confirmed":
            yield from _replan(conn, client, prev["id"], trip, prev["user_messages"], pending["changes"],
                               pending["message"])
            return
        if ev["type"] == "confirm_replan":
            conn.execute("UPDATE trips SET pending_replan = %s WHERE id = %s",
                         (Jsonb({k: ev[k] for k in ("changes", "message", "text")}), prev["id"]))
            log_message(conn, prev["id"], "ai", ev["text"])
            ev = {**ev, "trip_id": prev["id"]}
        elif ev["type"] == "itinerary":
            version = save_itinerary(conn, prev["id"], ev["itinerary"], ev["places"])
            log_message(conn, prev["id"], "ai", ev["itinerary"]["summary"], version)
            conn.execute("UPDATE trips SET user_messages = user_messages || %s WHERE id = %s", ([message], prev["id"]))
            ev = {**ev, "trip_id": prev["id"], "version": version}
        elif ev["type"] == "answer":
            log_message(conn, prev["id"], "ai", ev["text"])
        yield sse(ev)


def _replan(conn, client, trip_id: int, trip: Trip, user_messages: list[str], changes: dict, message: str):
    """Đổi Trip đã được đồng ý → lưu spec, lập lại với lịch cũ làm gợi ý."""
    try:
        trip = changed_trip(trip, changes)
    except ValidationError as e:
        yield sse({"type": "error", "message": e.errors()[0]["msg"].removeprefix("Value error, ")})
        return
    user_messages = [*user_messages, message]
    conn.execute("UPDATE trips SET spec = %s, user_messages = %s, pending_replan = NULL WHERE id = %s",
                 (Jsonb(trip.model_dump(mode="json")), user_messages, trip_id))
    dest = next(d for d in list_destinations(conn) if d["slug"] == trip.destination)
    latest = latest_itinerary(conn, trip_id)
    previous = (latest[1], itinerary_places(conn, latest[1])) if latest else None
    yield _trip_event(trip_id, trip, dest)
    yield from _plan_and_save(conn, client, trip_id, trip, dest, user_messages, previous)


def _run(conn, user_id: int, message: str, prev: dict | None = None):
    dests = {d["slug"]: d for d in list_destinations(conn)}
    client = llm.chat_client()
    user_messages = [*(prev["user_messages"] if prev else []), message]
    yield sse({"type": "thinking", "text": "Đang đọc yêu cầu của bạn…"})
    latest = latest_itinerary(conn, prev["id"]) if prev else None
    if latest:
        log_message(conn, prev["id"], "user", message)
        yield from _follow_up(conn, client, prev, latest[1], dests[prev["spec"]["destination"]], message)
        return
    try:
        trip = parse_trip(client, settings.llm_model, _parse_input(user_messages),
                          {slug: d["name"] for slug, d in dests.items()},
                          _today())
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
    log_message(conn, trip_id, "user", message)
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


class Replan(BaseModel):
    changes: dict
    message: str = Field(min_length=1, max_length=2000)


@router.post("/trips/{trip_id}/replan")
def replan_trip(trip_id: int, body: Replan, user_id: int = Depends(current_user), conn=Depends(get_conn)):
    """Người dùng xác nhận đổi Trip (event confirm_replan) → lập lại, gửi kèm lịch cũ làm gợi ý."""
    row = conn.execute("SELECT spec, user_messages FROM trips WHERE id = %s AND user_id = %s",
                       (trip_id, user_id)).fetchone()
    if not row:
        raise HTTPException(404, "Không tìm thấy chuyến đi")
    trip = Trip.model_validate(row["spec"])
    try:
        changed_trip(trip, body.changes)
    except ValidationError as e:
        raise HTTPException(422, e.errors()[0]["msg"].removeprefix("Value error, ")) from None
    return _stream(lambda c: _replan(c, llm.chat_client(), trip_id, trip, row["user_messages"], body.changes,
                                     body.message))


@router.get("/trips")
def list_trips(user_id: int = Depends(current_user), conn=Depends(get_conn)):
    return conn.execute(
        """SELECT t.id, t.spec, t.created_at, d.name AS destination_name
           FROM trips t LEFT JOIN destinations d ON d.slug = t.spec->>'destination'
           WHERE t.user_id = %s ORDER BY t.id DESC""", (user_id,)).fetchall()


@router.get("/trips/{trip_id}")
def get_trip(trip_id: int, version: int | None = None, user_id: int = Depends(current_user),
             conn=Depends(get_conn)):
    trip = conn.execute("SELECT id, spec, pinned_place_ids FROM trips WHERE id = %s AND user_id = %s",
                        (trip_id, user_id)).fetchone()
    if not trip:
        raise HTTPException(404, "Không tìm thấy chuyến đi")
    it = load_itinerary(conn, trip_id, version)
    if version is not None and not it:
        raise HTTPException(404, "Không tìm thấy phiên bản lịch trình")
    versions = [r["version"] for r in conn.execute(
        "SELECT version FROM itineraries WHERE trip_id = %s ORDER BY version", (trip_id,)).fetchall()]
    dest = next(d for d in list_destinations(conn) if d["slug"] == trip["spec"]["destination"])
    return {"trip_id": trip["id"], "trip": trip["spec"], "center": [dest["lon"], dest["lat"]],
            "version": it[0] if it else None,
            "itinerary": it[1].model_dump(mode="json") if it else None,
            "places": it[2] if it else {}, "versions": versions, "pinned_place_ids": trip["pinned_place_ids"]}

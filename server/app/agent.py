import datetime as dt
import json
from collections.abc import Iterator

from pydantic import ValidationError

from app.domain import KINDS, PACE_HOURS, PACE_STOPS, TAGS, Draft, Itinerary, Place, Trip
from app.places import search_places
from app.rules import InvalidDraft, build_itinerary, vnd


class UnsupportedDestination(Exception):
    pass


class TripParseError(Exception):
    pass


PARSE_PROMPT = """Hôm nay là {today}. Chuyển yêu cầu du lịch của người dùng thành Trip bằng tool record_trip.
Destination hỗ trợ: {dests}. Nếu người dùng muốn đi nơi khác, destination = "unsupported".
Budget tính bằng VND cho cả nhóm ("3 triệu" = 3000000). Nếu không nói, ước lượng 1500000 × số người × số ngày.
Chỉ điền start_date (YYYY-MM-DD) khi người dùng nói rõ ngày đi.
Pace: "nhẹ nhàng/thong thả" = thong-tha, "đi nhiều/khám phá hết" = day, còn lại = vua.
Chỉ dùng Tag trong danh sách cho phép; Tag người dùng nói không muốn → avoided_tags."""


def _trip_tool(dest_slugs: list[str]) -> dict:
    tag_list = {"type": "array", "items": {"type": "string", "enum": sorted(TAGS)}}
    return {"type": "function", "function": {
        "name": "record_trip", "description": "Ghi lại Trip của người dùng",
        "parameters": {"type": "object", "properties": {
            "destination": {"type": "string", "enum": [*dest_slugs, "unsupported"]},
            "days": {"type": "integer"},
            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
            "budget": {"type": "integer", "description": "VND cho cả nhóm"},
            "travelers": {"type": "integer"},
            "required_tags": tag_list, "preferred_tags": tag_list, "avoided_tags": tag_list,
            "pace": {"type": "string", "enum": ["thong-tha", "vua", "day"]},
            "travel_mode": {"type": "string", "enum": ["xe-may", "grab"]},
        }, "required": ["destination", "days", "budget"]},
    }}


def parse_trip(client, model: str, message: str, destinations: dict[str, str], today: dt.date) -> Trip:
    dests = ", ".join(f"{slug} ({name})" for slug, name in destinations.items())
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": PARSE_PROMPT.format(today=today.isoformat(), dests=dests)},
                  {"role": "user", "content": message}],
        tools=[_trip_tool(list(destinations))],
        tool_choice="required",
    )
    calls = r.choices[0].message.tool_calls or []
    if not calls:
        raise TripParseError("AI chưa hiểu yêu cầu, bạn nói rõ hơn điểm đến, số ngày và ngân sách nhé.")
    try:
        args = json.loads(calls[0].function.arguments)
    except json.JSONDecodeError as e:
        raise TripParseError("AI trả về dữ liệu hỏng, thử lại nhé.") from e
    if args.get("destination") not in destinations:
        raise UnsupportedDestination(
            f"Travility chưa hỗ trợ điểm đến này. Hiện có: {', '.join(destinations.values())}.")
    try:
        return Trip.model_validate(args)
    except ValidationError as e:
        raise TripParseError("Chưa lập được Trip: hỗ trợ 1–7 ngày, 1–10 người và ngân sách lớn hơn 0.") from e


MAX_STEPS = 12
MAX_INVALID = 1  # Place lạ / Draft sai: cho AI làm lại 1 lần (ADR-0001)

PLAN_PROMPT = """Bạn là trợ lý lập lịch trình du lịch cho người Việt.
Quy tắc:
- Chỉ dùng place_id nhận được từ search_places. Không bao giờ tự nghĩ ra địa điểm.
- Gọi search_places nhiều lần cho từng nhu cầu: ăn sáng, tham quan, cafe, ăn tối, và chỗ ở (kind=cho-o) nếu Trip dài hơn 1 ngày.
- Mỗi ngày số Stop và khung giờ theo Pace trong đề bài; sắp Stop theo thứ tự địa lý hợp lý, tránh đi vòng.
- Tôn trọng Tag bắt buộc, tránh Tag cần tránh. Ngày khả năng mưa cao thì ưu tiên Place trong nhà (outdoor=false).
- Kiểm tra open_hours của Place khi xếp giờ.
- reason: 1 câu tiếng Việt nêu vì sao chọn, nhắc Tag/sở thích liên quan.
- Không tự tính tiền: hệ thống tự tính và báo Conflict.
- Khi đủ thông tin, gọi submit_itinerary. summary: 1–2 câu tiếng Việt thân thiện tóm tắt chuyến đi."""

PLAN_TOOLS = [
    {"type": "function", "function": {
        "name": "search_places",
        "description": "Tìm Place thật trong Destination của Trip. Chỉ được dùng place_id trả về từ tool này.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Mô tả tự nhiên, vd 'quán cafe yên tĩnh view đồi thông'"},
            "kind": {"type": "string", "enum": list(KINDS)},
            "must_have_tags": {"type": "array", "items": {"type": "string", "enum": sorted(TAGS)}},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "submit_itinerary",
        "description": "Nộp Itinerary hoàn chỉnh.",
        "parameters": {"type": "object", "properties": {
            "stay_place_id": {"type": "integer", "description": "Place kind cho-o; bắt buộc nếu Trip > 1 ngày"},
            "summary": {"type": "string"},
            "days": {"type": "array", "items": {"type": "object", "properties": {
                "stops": {"type": "array", "items": {"type": "object", "properties": {
                    "place_id": {"type": "integer"},
                    "start_time": {"type": "string", "description": "HH:MM"},
                    "duration_min": {"type": "integer"},
                    "reason": {"type": "string"},
                }, "required": ["place_id", "start_time", "duration_min", "reason"]}},
            }, "required": ["stops"]}},
        }, "required": ["days", "summary"]},
    }},
]


def trip_brief(trip: Trip, rain: list[int | None] | None) -> str:
    lo, hi = PACE_STOPS[trip.pace]
    start, end = PACE_HOURS[trip.pace]
    when = f", bắt đầu {trip.start_date.isoformat()}" if trip.start_date else ""
    lines = [
        f"Destination: {trip.destination}",
        f"Số ngày: {trip.days}{when}",
        f"Số người: {trip.travelers}",
        f"Budget: {vnd(trip.budget)}",
        f"Pace: {lo}-{hi} Stop/ngày, từ {start} đến {end}",
        f"Travel Mode: {trip.travel_mode}",
        f"Tag bắt buộc: {', '.join(trip.required_tags) or 'không'}",
        f"Tag ưu tiên: {', '.join(trip.preferred_tags) or 'không'}",
        f"Tag cần tránh: {', '.join(trip.avoided_tags) or 'không'}",
    ]
    if rain:
        chances = ", ".join(f"ngày {i + 1}: {'?' if r is None else str(r) + '%'}" for i, r in enumerate(rain))
        lines.append(f"Khả năng mưa: {chances}")
    return "\n".join(lines)


def place_brief(p: Place) -> dict:
    return {"id": p.id, "name": p.name, "kind": p.kind, "lat": p.lat, "lon": p.lon,
            "photo_url": p.photo_url, "outdoor": p.outdoor, "price": p.price}


def _for_llm(p: Place) -> dict:
    return {"place_id": p.id, "name": p.name, "kind": p.kind, "tags": p.tags, "price": p.price,
            "outdoor": p.outdoor, "open_hours": p.open_hours, "lat": round(p.lat, 4), "lon": round(p.lon, 4)}


def _itinerary_event(itin: Itinerary, seen: dict[int, Place]) -> dict:
    used = {s.place_id for d in itin.days for s in d.stops}
    if itin.stay_place_id is not None:
        used.add(itin.stay_place_id)
    return {"type": "itinerary", "itinerary": itin.model_dump(mode="json"),
            "places": {str(i): place_brief(seen[i]) for i in used}}


def plan(conn, client, model: str, trip: Trip, embed_fn, rain: list[int | None] | None) -> Iterator[dict]:
    seen: dict[int, Place] = {}  # chỉ Place AI đã nhận từ search_places mới hợp lệ
    messages = [{"role": "system", "content": PLAN_PROMPT},
                {"role": "user", "content": trip_brief(trip, rain)}]
    submits = invalid = 0
    last: Itinerary | None = None

    for _ in range(MAX_STEPS):
        r = client.chat.completions.create(model=model, messages=messages, tools=PLAN_TOOLS,
                                           tool_choice="required")
        msg = r.choices[0].message
        calls = msg.tool_calls or []
        if msg.content:
            yield {"type": "thinking", "text": msg.content}
        assistant = {"role": "assistant", "content": msg.content}
        if calls:
            assistant["tool_calls"] = [{"id": c.id, "type": "function",
                                        "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                       for c in calls]
        messages.append(assistant)

        final = None
        for c in calls:
            try:
                args = json.loads(c.function.arguments or "{}")
            except json.JSONDecodeError:
                args = None

            if not isinstance(args, dict):
                result = "Lỗi: arguments không phải JSON object hợp lệ."
            elif c.function.name == "search_places":
                query = str(args.get("query", ""))
                found = search_places(
                    conn, trip.destination, embed_fn([query])[0], kind=args.get("kind"),
                    must_have_tags=[t for t in args.get("must_have_tags", []) if t in TAGS],
                    exclude_tags=trip.avoided_tags)
                seen.update({p.id: p for p in found})
                yield {"type": "tool_call", "name": "search_places", "query": query,
                       "places": [place_brief(p) for p in found]}
                result = json.dumps([_for_llm(p) for p in found], ensure_ascii=False)
            elif c.function.name == "submit_itinerary":
                try:
                    itin = build_itinerary(trip, Draft.model_validate(args), seen, rain)
                except (ValidationError, InvalidDraft) as e:
                    invalid += 1
                    if invalid > MAX_INVALID:
                        yield {"type": "error", "message": "AI chưa lập được lịch trình hợp lệ, bạn thử lại nhé."}
                        return
                    result = f"Lỗi: {e}. Chỉ dùng place_id đã nhận từ search_places."
                else:
                    submits += 1
                    last = itin
                    if not itin.conflicts or submits >= 2:
                        final = itin
                    result = ("Conflict: " + "; ".join(x.message for x in itin.conflicts)
                              + ". Sửa nếu có thể rồi submit lại; nếu không thể thì submit lại y nguyên.")
            else:
                result = f"Lỗi: không có tool {c.function.name}."
            messages.append({"role": "tool", "tool_call_id": c.id, "content": result})

        if final:
            yield _itinerary_event(final, seen)
            return

    if last:  # hết lượt nhưng đã có phương án → trả phương án tốt nhất (best-effort)
        yield _itinerary_event(last, seen)
    else:
        yield {"type": "error", "message": "AI chưa hoàn thành lịch trình, bạn thử lại nhé."}

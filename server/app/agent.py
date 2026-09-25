import datetime as dt
import json

from pydantic import ValidationError

from app.domain import TAGS, Trip


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

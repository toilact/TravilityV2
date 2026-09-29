"""Tin nhắn tiếp theo trên Trip đã có lịch trình: trả lời, sửa bằng thao tác, hoặc xin lập lại (#22)."""
import json
from collections.abc import Iterator

from app.agent import MAX_STEPS, PLAN_TOOLS, run_search, trip_brief
from app.domain import INTENT_LABELS, WEEKDAYS, Hub, Itinerary, Place, Trip
from app.rules import cost_breakdown, vnd

FOLLOWUP_PROMPT = """Bạn là trợ lý của một chuyến đi đã có lịch trình. Đọc tin nhắn mới và chọn đúng MỘT việc:
- Câu hỏi, nhận xét, lời cảm ơn → gọi answer. Chỉ dùng số liệu trong phần "Dữ kiện"; thiếu dữ liệu thì nói rõ app chưa có, không đoán, không bịa số.
Trả lời tiếng Việt, ngắn gọn, thân thiện."""

ANSWER_TOOL = {"type": "function", "function": {
    "name": "answer", "description": "Trả lời người dùng, KHÔNG đổi lịch trình.",
    "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}}


def _km_min_cost(legs) -> tuple[float, int, int]:
    return sum(x.distance_km for x in legs), sum(x.duration_min for x in legs), sum(x.cost for x in legs)


def itinerary_facts(trip: Trip, itin: Itinerary, places: dict[int, Place]) -> str:
    """Số liệu do code tính để LLM trả lời câu hỏi — LLM không tự tính hay đoán."""
    lines = []
    if itin.stay_place_id is not None:
        lines.append(f"Chỗ ở: {places[itin.stay_place_id].name} (place_id {itin.stay_place_id})")
    for di, day in enumerate(itin.days):
        wd = WEEKDAYS[day.date.weekday()] if day.date else None
        rain = "không có dự báo" if day.rain_chance is None else f"khả năng mưa {day.rain_chance}%"
        km, mins, cost = _km_min_cost(day.legs)
        date = f" ({day.date.isoformat()})" if day.date else ""
        lines.append(f"Ngày {di + 1}{date}: {rain}; di chuyển {km:.1f} km, {mins} phút, {vnd(cost)}")
        for si, s in enumerate(day.stops):
            p = places[s.place_id]
            hours = p.open_hours.get(wd) if wd and p.open_hours else None
            extra = [p.kind, vnd(s.est_cost), "ngoài trời" if p.outdoor else "trong nhà"]
            if hours:
                extra.append(f"mở {hours[0]}–{hours[1]}")
            if s.pinned:
                extra.append("đã ghim")
            lines.append(f"  [{di}.{si}] {s.start_time}, {s.duration_min} phút: {p.name} "
                         f"(place_id {p.id}; {', '.join(extra)})")
    km, mins, _ = _km_min_cost([x for d in itin.days for x in d.legs])
    b = cost_breakdown(trip, itin, places)
    lines += [
        f"Tổng di chuyển: {km:.1f} km, {mins} phút",
        f"Tổng chi phí {vnd(itin.total_cost)} = ăn uống {vnd(b['an_uong'])} + vé/tham quan {vnd(b['tham_quan'])}"
        f" + chỗ ở {vnd(b['cho_o'])} + di chuyển {vnd(b['di_chuyen'])}; Budget {vnd(trip.budget)}, "
        + (f"còn {vnd(left)}" if (left := trip.budget - itin.total_cost) >= 0 else f"vượt {vnd(-left)}"),
    ]
    if itin.conflicts:
        lines.append("Xung đột: " + "; ".join(c.message for c in itin.conflicts))
    if itin.intents:
        lines.append("Mục đích: " + ", ".join(f"{INTENT_LABELS[k]} {'có' if v else 'thiếu'}"
                                             for k, v in itin.intents.items()))
    lines.append("App KHÔNG có dữ liệu: nhiệt độ, giá vé thật hôm đó, kẹt xe, đánh giá của khách.")
    return "\n".join(lines)


def followup(conn, client, model: str, trip: Trip, itin: Itinerary, places: dict[int, Place], message: str,
             rain: list[int | None] | None, hub: Hub | None, embed_fn) -> Iterator[dict]:
    seen = dict(places)  # Place đang có trong lịch + Place AI tìm thêm
    tools = [PLAN_TOOLS[0], ANSWER_TOOL]
    messages = [{"role": "system", "content": FOLLOWUP_PROMPT},
                {"role": "user", "content": f"{trip_brief(trip, rain, hub)}\n\nDữ kiện lịch trình hiện tại:\n"
                                            f"{itinerary_facts(trip, itin, places)}\n\nTin nhắn mới: {message}"}]
    for _ in range(MAX_STEPS):
        msg = client.chat.completions.create(model=model, messages=messages, tools=tools,
                                             tool_choice="required").choices[0].message
        messages.append(msg.model_dump(exclude_none=True))  # Gemini 3 cần thought_signature
        for c in msg.tool_calls or []:
            try:
                args = json.loads(c.function.arguments or "{}")
            except json.JSONDecodeError:
                args = None
            if not isinstance(args, dict):
                result = "Lỗi: arguments không phải JSON object hợp lệ."
            elif c.function.name == "search_places":
                ev, result = run_search(conn, trip, embed_fn, args, seen)
                yield ev
            elif c.function.name == "answer":
                yield {"type": "answer", "text": str(args.get("text", ""))}
                return
            else:
                result = f"Lỗi: không có tool {c.function.name}."
            messages.append({"role": "tool", "tool_call_id": c.id, "content": result})
    yield {"type": "error", "message": "AI chưa xử lý xong tin nhắn, bạn thử lại nhé."}

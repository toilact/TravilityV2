"""Lập lịch đa agent (spec scale §7): ba chuyên gia tìm Place song song, agent tổng hợp xếp lịch."""
import copy
import json

from app.agent import PLAN_TOOLS, run_search, trip_brief
from app.domain import PACE_STOPS, Place, Trip

# role → (nhãn, các kind được chọn, việc cần làm)
ROLES = {
    "an-uong": ("Ăn uống", ("an-uong",),
                "quán ăn cho bữa sáng, trưa, tối; ưu tiên quán ăn no bụng cho bữa trưa và tối"),
    "tham-quan": ("Tham quan", ("tham-quan", "cafe", "giai-tri"),
                  "điểm tham quan, cafe, giải trí; ngày khả năng mưa cao thì ưu tiên Place trong nhà (outdoor=false)"),
    "cho-o": ("Chỗ ở", ("cho-o",), "chỗ ở hợp Budget và Tag"),
}
MAX_SEARCHES = 4

SPECIALIST_PROMPT = """Bạn là chuyên gia {label} trong nhóm lập lịch du lịch cho người Việt.
Việc của bạn: chọn danh sách ngắn khoảng {n} Place — {task}. Một agent khác sẽ xếp lịch từ danh sách này.
Quy tắc:
- Chỉ dùng place_id nhận được từ search_places. Không bao giờ tự nghĩ ra địa điểm.
- Gọi search_places tối đa {max} lần, mỗi lần cho một nhu cầu khác nhau.
- Tôn trọng Tag bắt buộc, tránh Tag cần tránh, cân Budget của cả chuyến.
- Xong thì gọi submit_shortlist. note: 1 câu tiếng Việt gợi ý cách dùng danh sách (vd quán nào hợp bữa nào)."""


class AgentFailed(Exception):
    pass


def roles_for(trip: Trip) -> list[str]:
    return [r for r in ROLES if r != "cho-o" or trip.days > 1]


def wanted(trip: Trip, role: str) -> int:
    """Cỡ danh sách ngắn (spec §7): 2 × số bữa; 2 × số Stop còn lại theo Pace; 3 chỗ ở."""
    meals = 3 * trip.days
    if role == "an-uong":
        return 2 * meals
    if role == "cho-o":
        return 3
    return 2 * max(PACE_STOPS[trip.pace][1] * trip.days - meals, trip.days)


def _tools(kinds: tuple[str, ...]) -> list[dict]:
    search = copy.deepcopy(PLAN_TOOLS[0])
    search["function"]["parameters"]["properties"]["kind"]["enum"] = list(kinds)
    return [search, {"type": "function", "function": {
        "name": "submit_shortlist", "description": "Nộp danh sách ngắn các Place đã chọn.",
        "parameters": {"type": "object", "properties": {
            "place_ids": {"type": "array", "items": {"type": "integer"}},
            "note": {"type": "string"},
        }, "required": ["place_ids", "note"]},
    }}]


def shortlist(conn, client, model: str, trip: Trip, role: str, embed_fn, rain, user_messages: list[str], emit) -> dict:
    """Một chuyên gia: tìm Place trong các kind của role rồi nộp danh sách ngắn {"role", "place_ids", "note"}.

    Mỗi lượt tìm gọi emit(event tool_call kèm agent=role). Không nộp được danh sách hợp lệ → AgentFailed.
    """
    label, kinds, task = ROLES[role]
    seen: dict[int, Place] = {}
    messages = [{"role": "system", "content": SPECIALIST_PROMPT.format(label=label, n=wanted(trip, role), task=task,
                                                                      max=MAX_SEARCHES)},
                {"role": "user", "content": trip_brief(trip, rain, None, user_messages)}]
    searches = 0
    for _ in range(MAX_SEARCHES + 2):
        r = client.chat.completions.create(model=model, messages=messages, tools=_tools(kinds), tool_choice="required")
        msg = r.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))  # nguyên message: Gemini cần thought_signature
        for c in msg.tool_calls or []:
            try:
                args = json.loads(c.function.arguments or "{}")
            except json.JSONDecodeError:
                args = None
            if not isinstance(args, dict):
                result = "Lỗi: arguments không phải JSON object hợp lệ."
            elif c.function.name == "search_places":
                searches += 1
                if searches > MAX_SEARCHES:
                    result = "Lỗi: hết lượt tìm. Gọi submit_shortlist với Place đã có."
                else:  # ADR-0001: code ép kind theo role, không tin LLM
                    kind = kinds[0] if len(kinds) == 1 else args.get("kind") if args.get("kind") in kinds else None
                    ev, result = run_search(conn, trip, embed_fn, {**args, "kind": kind}, seen, kinds)
                    emit({**ev, "agent": role})
            elif c.function.name == "submit_shortlist":
                ids = [i for i in dict.fromkeys(args.get("place_ids") or []) if i in seen]
                if ids:
                    return {"role": role, "place_ids": ids, "note": str(args.get("note") or "")}
                result = "Lỗi: danh sách rỗng. Chỉ dùng place_id đã nhận từ search_places."
            else:
                result = f"Lỗi: không có tool {c.function.name}."
            messages.append({"role": "tool", "tool_call_id": c.id, "content": result})
    raise AgentFailed(f"agent {role} không nộp được danh sách ngắn")

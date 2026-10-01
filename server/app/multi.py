"""Lập lịch đa agent (spec scale §7): ba chuyên gia tìm Place song song, agent tổng hợp xếp lịch."""
import copy
import json
import logging
import queue
import threading
import time
from collections.abc import Iterator

from app import agent
from app.agent import PLAN_TOOLS, for_llm, run_search, trip_brief
from app.db import connect
from app.domain import PACE_STOPS, Place, Trip
from app.places import get_places

logger = logging.getLogger(__name__)
_now = time.monotonic
agent_conn = connect  # mỗi chuyên gia một kết nối riêng; test thay bằng kết nối test
AGENT_WAIT_S = 45  # chờ đủ danh sách tối đa bấy nhiêu giây rồi quay về agent đơn
FALLBACK_TEXT = "Chuyển sang lập lịch thường…"

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


def _work(put, client, model: str, trip: Trip, role: str, embed_fn, rain, user_messages: list[str]) -> None:
    """Chạy một chuyên gia; event, kết quả hoặc lỗi {"role", "error"} đều đi qua put."""
    try:
        with agent_conn() as conn:
            put(shortlist(conn, client, model, trip, role, embed_fn, rain, user_messages, put))
    except Exception as e:  # lỗi nào cũng thành "agent lỗi": điều phối quay về agent đơn
        logger.warning("agent %s lỗi: %s", role, e)
        put({"role": role, "error": str(e)})


def _local(client, model: str, trip: Trip, embed_fn, rain, user_messages: list[str], roles: list[str]):
    """Không có Redis: mỗi chuyên gia một thread trong tiến trình, thông điệp về qua Queue.

    ponytail: thread quá hạn không huỷ được, chạy nền tới khi xong rồi kết quả bị bỏ.
    """
    q: queue.Queue = queue.Queue()
    for role in roles:
        threading.Thread(target=_work, args=(q.put, client, model, trip, role, embed_fn, rain, user_messages),
                         daemon=True).start()

    def recv(timeout: float) -> dict | None:
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            return None

    return recv


def gather(recv, roles: list[str]):
    """Phát lại event của các chuyên gia; return danh sách kết quả, hoặc None khi có agent lỗi hay quá hạn."""
    deadline, results = _now() + AGENT_WAIT_S, []
    while len(results) < len(roles):
        left = deadline - _now()
        if left <= 0:
            return None
        m = recv(min(left, 0.5))
        if m is None:
            continue
        if "type" in m:
            yield m
        elif "error" in m:
            return None
        else:
            results.append(m)
    return results


def _notes(results: list[dict], places: dict[int, Place]) -> str:
    lines = ["Các chuyên gia đã chọn sẵn Place dưới đây (place_id dùng được luôn). Ưu tiên dùng các Place này; "
             "chỉ gọi search_places khi còn thiếu, tối đa 2 lần."]
    for r in results:
        lines.append(f"{ROLES[r['role']][0]} — {r['note']}")
        lines.append(json.dumps([for_llm(places[i]) for i in r["place_ids"] if i in places], ensure_ascii=False))
    return "\n".join(lines)


def plan(conn, client, model: str, trip: Trip, embed_fn, rain, hub=None, user_messages: list[str] = (),
         previous=None, local: bool = False) -> Iterator[dict]:
    """Cùng hợp đồng với agent.plan. Thiếu danh sách của bất kỳ chuyên gia nào → agent đơn nguyên bản (spec §7)."""
    roles = roles_for(trip)
    yield {"type": "thinking", "text": "Các chuyên gia đang tìm địa điểm…"}
    recv = _local(client, model, trip, embed_fn, rain, list(user_messages), roles)
    results = yield from gather(recv, roles)
    if results is None:
        yield {"type": "thinking", "text": FALLBACK_TEXT}
        yield from agent.plan(conn, client, model, trip, embed_fn, rain, hub, user_messages, previous)
        return
    seeded = get_places(conn, [i for r in results for i in r["place_ids"]])
    yield from agent.plan(conn, client, model, trip, embed_fn, rain, hub, user_messages, previous,
                          seeded=seeded, notes=_notes(results, seeded), max_searches=2)

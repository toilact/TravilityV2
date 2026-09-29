"""Engine thay thế theo mục đích (spec 2026-09-29-revision-giu-muc-dich §4, ADR-0006). Code thuần, không gọi LLM."""
from collections.abc import Callable

from pydantic import BaseModel

from app.domain import (DEFAULT_TRAVEL_MODE, INTENT_LABELS, WEEKDAYS, Day, Disruption, Draft, DraftDay, DraftStop, Hub,
                        Itinerary, Place, Trip, intent_weights, place_intents)
from app.rules import _minutes, build_itinerary, haversine_km, is_open, make_leg, vnd

N_OPTIONS = 3
HARD = {"closed", "before_arrival", "after_departure", "over_budget"}
KIND_TEXT = {"closed": "đóng cửa", "disliked": "bạn muốn đổi"}


class InvalidDisruption(Exception):
    pass


class NoFeasible(BaseModel):
    reason_codes: list[str]


class ProposalOption(BaseModel):
    itinerary: Itinerary
    added: list[Place]
    changed: list[tuple[int, int]]  # (day_index, stop_index)
    metrics: dict
    reason_codes: list[str]
    explanation: str


CandidatesFn = Callable[[Place, set[int]], list[Place]]
Point = Place | Hub | None


def to_draft(itin: Itinerary) -> Draft:
    return Draft(stay_place_id=itin.stay_place_id, summary=itin.summary, days=[
        DraftDay(stops=[DraftStop(**s.model_dump(exclude={"est_cost"})) for s in d.stops]) for d in itin.days])


def _leg_min(a: Point, b: Point, trip: Trip) -> int:
    if a is None or b is None:
        return 0
    return make_leg(a, b, trip.travel_mode or DEFAULT_TRAVEL_MODE, trip.travelers).duration_min


def features(trip: Trip, lost: Place, cand: Place, prev: Point, nxt: Point) -> dict:
    """Đặc trưng của một ứng viên — đầu vào chung của score() và ranker ML (lát E2)."""
    w = intent_weights(trip)
    li, ci = place_intents(lost.tags), place_intents(cand.tags)
    lw = sum(w.get(i, 1) for i in li)
    lt, ct = set(lost.tags), set(cand.tags)
    return {
        "intent_overlap": sum(w.get(i, 1) for i in li & ci) / lw if lw else 0.0,
        "tag_jaccard": len(lt & ct) / len(lt | ct) if lt | ct else 0.0,
        "extra_travel_min": (_leg_min(prev, cand, trip) + _leg_min(cand, nxt, trip)
                             - _leg_min(prev, lost, trip) - _leg_min(lost, nxt, trip)),
        "extra_cost_vnd": (cand.price - lost.price) * trip.travelers,
        "price_ratio": cand.price / lost.price if lost.price else 1.0,
        "distance_km_from_lost": round(haversine_km(lost, cand), 2),
        "outdoor": int(cand.outdoor),
    }


def score(f: dict) -> float:
    # Hệ số ước lượng ban đầu; lát E1 chỉnh, lát E2 có thể thay bằng ranker cùng chữ ký.
    return 3 * f["intent_overlap"] + f["tag_jaccard"] - f["extra_travel_min"] / 30 - f["extra_cost_vnd"] / 200_000


def _neighbors(itin: Itinerary, places: dict[int, Place], di: int, si: int, hub: Hub | None) -> tuple[Point, Point]:
    day, last = itin.days[di], len(itin.days) - 1
    stay = places.get(itin.stay_place_id) if itin.stay_place_id is not None else None
    prev = places[day.stops[si - 1].place_id] if si > 0 else (hub if hub and di == 0 else stay)
    nxt = places[day.stops[si + 1].place_id] if si + 1 < len(day.stops) else (hub if hub and di == last else stay)
    return prev, nxt


def _reject(trip: Trip, day: Day, si: int, lost: Place, cand: Place, prev: Point, nxt: Point) -> str | None:
    stop = day.stops[si]
    weekdays = [WEEKDAYS[day.date.weekday()]] if day.date else WEEKDAYS
    if not any(is_open(cand, w, stop.start_time, stop.duration_min) for w in weekdays):
        return "NO_OPEN_CANDIDATE"
    start = _minutes(stop.start_time)
    # Không bắt lịch chặt hơn bản cũ: chỉ loại khi chặng mới vừa vượt khoảng trống vừa dài hơn chặng cũ.
    if si > 0:
        p = day.stops[si - 1]
        need = _leg_min(prev, cand, trip)
        if need > start - (_minutes(p.start_time) + p.duration_min) and need > _leg_min(prev, lost, trip):
            return "NOT_REACHABLE_IN_TIME"
    if si + 1 < len(day.stops):
        need = _leg_min(cand, nxt, trip)
        if need > _minutes(day.stops[si + 1].start_time) - start - stop.duration_min and need > _leg_min(lost, nxt, trip):
            return "NOT_REACHABLE_IN_TIME"
    return None


def _hard(itin: Itinerary) -> set[tuple[str, int | None]]:
    return {(c.kind, c.day_index) for c in itin.conflicts if c.kind in HARD}


def _stop_intents(trip: Trip, p: Place) -> set[str]:
    """Intent của Place mà Trip quan tâm; Trip không có Intent nào thì lấy mọi Intent của Place."""
    w = intent_weights(trip)
    return place_intents(p.tags) & w.keys() if w else place_intents(p.tags)


def _labels(intents) -> str:
    return ", ".join(INTENT_LABELS[i] for i in sorted(intents))


def _travel_min(itin: Itinerary) -> int:
    return sum(leg.duration_min for d in itin.days for leg in d.legs)


def _day_end(day: Day) -> str:
    m = max(_minutes(s.start_time) + s.duration_min for s in day.stops)
    return f"{m // 60:02d}:{m % 60:02d}"


def _explain(kept: set, lost: set, travel_delta: int, cost_delta: int, day_end: str, di: int) -> str:
    parts = []
    if kept:
        parts.append(f"giữ mục đích {_labels(kept)}")
    if lost:
        parts.append(f"chuyến không còn {_labels(lost)}")
    parts.append("thời gian di chuyển như cũ" if travel_delta == 0
                 else f"{'thêm' if travel_delta > 0 else 'bớt'} {abs(travel_delta)} phút di chuyển")
    parts.append("chi phí như cũ" if cost_delta == 0
                 else f"{'đắt hơn' if cost_delta > 0 else 'rẻ hơn'} {vnd(abs(cost_delta))}")
    parts.append(f"ngày {di + 1} kết thúc {day_end}")
    s = "; ".join(parts)
    return s[0].upper() + s[1:] + "."


def _option(trip: Trip, old: Itinerary, new: Itinerary, at: tuple[int, int], lost: Place, cand: Place,
            prev: Point, nxt: Point) -> ProposalOption:
    li = _stop_intents(trip, lost)
    kept = li & place_intents(cand.tags)
    # "không còn" chỉ khi cả chuyến mất Intent đó, không phải khi Stop khác vẫn đáp ứng
    lost_trip = {k for k, hit in old.intents.items() if hit and not new.intents.get(k)}
    cost_delta = new.total_cost - old.total_cost
    travel_delta = _travel_min(new) - _travel_min(old)
    di = at[0]
    codes = []
    if li:
        codes.append("INTENT_MATCH" if kept == li else "INTENT_PARTIAL" if kept else "INTENT_LOST")
    if travel_delta > 5:
        codes.append("FARTHER")
    elif travel_delta < -5:
        codes.append("CLOSER")
    if cost_delta > 0:
        codes.append("PRICIER")
    elif cost_delta < 0:
        codes.append("CHEAPER")
    day_end = _day_end(new.days[di])
    metrics = {"cost_delta": cost_delta, "travel_min_delta": travel_delta,
               "day_end_before": _day_end(old.days[di]), "day_end_after": day_end,
               "retention_before": old.retention, "retention_after": new.retention,
               "intents_kept": sorted(kept), "intents_lost": sorted(lost_trip),
               "features": features(trip, lost, cand, prev, nxt)}
    return ProposalOption(itinerary=new, added=[cand], changed=[at], metrics=metrics, reason_codes=codes,
                          explanation=_explain(kept, lost_trip, travel_delta, cost_delta, day_end, di))


def propose(trip: Trip, itin: Itinerary, places: dict[int, Place], d: Disruption, candidates_fn: CandidatesFn,
            hub: Hub | None = None, score_fn=score) -> list[ProposalOption] | NoFeasible:
    if d.day_index >= len(itin.days) or d.stop_index >= len(itin.days[d.day_index].stops):
        raise InvalidDisruption("Không tìm thấy Stop này trong lịch trình")
    day = itin.days[d.day_index]
    stop = day.stops[d.stop_index]
    if stop.pinned:
        raise InvalidDisruption("Stop đã ghim — bỏ ghim để đổi")
    lost = places[stop.place_id]
    used = {s.place_id for x in itin.days for s in x.stops}
    if itin.stay_place_id is not None:
        used.add(itin.stay_place_id)
    prev, nxt = _neighbors(itin, places, d.day_index, d.stop_index, hub)

    rejected, ok = [], []
    for c in candidates_fn(lost, used):
        why = _reject(trip, day, d.stop_index, lost, c, prev, nxt)
        (rejected.append(why) if why else ok.append(c))
    ok.sort(key=lambda c: score_fn(features(trip, lost, c, prev, nxt)), reverse=True)

    rain = [x.rain_chance for x in itin.days]
    old_hard = _hard(itin)
    options: list[ProposalOption] = []
    for c in ok:
        if len(options) == N_OPTIONS:
            break
        draft = to_draft(itin)
        kept = _stop_intents(trip, lost) & place_intents(c.tags)
        draft.days[d.day_index].stops[d.stop_index] = DraftStop(
            place_id=c.id, start_time=stop.start_time, duration_min=stop.duration_min,
            reason=f"Thay {lost.name} ({KIND_TEXT[d.kind]})" + (f" — cùng mục đích {_labels(kept)}" if kept else ""))
        new = build_itinerary(trip, draft, places | {c.id: c}, rain, hub)
        extra = _hard(new) - old_hard
        if extra:
            rejected.append("OVER_BUDGET" if ("over_budget", None) in extra else "NEW_CONFLICT")
            continue
        options.append(_option(trip, itin, new, (d.day_index, d.stop_index), lost, c, prev, nxt))
    return options or NoFeasible(reason_codes=sorted(set(rejected)) or ["NO_CANDIDATE"])

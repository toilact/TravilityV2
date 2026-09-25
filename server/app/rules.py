import datetime as dt
import math

from app.domain import WEEKDAYS, Conflict, Day, Draft, Itinerary, Leg, Place, Stop, Trip

# ponytail: đường chim bay × 1.3 thay cho quãng đường thật; đổi sang Goong Distance Matrix nếu cần chính xác.
ROAD_FACTOR = 1.3
WALK_MAX_KM = 0.8
SPEED_KMH = {"walk": 4.5, "xe-may": 25, "grab": 25}
FUEL_PER_KM = 2_000
GRAB_BASE, GRAB_PER_KM = 12_000, 9_000
MOTO_RENT_PER_DAY = 120_000
RAIN_PCT = 60


class InvalidDraft(Exception):
    pass


def vnd(n: int) -> str:
    return f"{n:,}".replace(",", ".") + "đ"


def haversine_km(a: Place, b: Place) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def make_leg(a: Place, b: Place, mode: str, travelers: int) -> Leg:
    km = round(haversine_km(a, b) * ROAD_FACTOR, 2)
    if km < WALK_MAX_KM:
        m, cost = "walk", 0
    elif mode == "grab":
        m, cost = "grab", (GRAB_BASE + round(km * GRAB_PER_KM)) * math.ceil(travelers / 4)
    else:
        m, cost = "xe-may", round(km * FUEL_PER_KM) * math.ceil(travelers / 2)
    return Leg(from_place_id=a.id, to_place_id=b.id, distance_km=km,
               duration_min=max(1, round(km / SPEED_KMH[m] * 60)), mode=m, cost=cost)


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def is_open(place: Place, weekday: str, start: str, duration_min: int) -> bool:
    if not place.open_hours:
        return True
    hours = place.open_hours.get(weekday)
    if not hours:
        return False
    o, c = _minutes(hours[0]), _minutes(hours[1])
    if c <= o:  # mở qua đêm, vd 18:00–02:00
        c = 24 * 60
    s = _minutes(start)
    return o <= s and s + duration_min <= c


def _check_draft(trip: Trip, draft: Draft, places: dict[int, Place]) -> None:
    ids = {s.place_id for d in draft.days for s in d.stops}
    if draft.stay_place_id is not None:
        ids.add(draft.stay_place_id)
    unknown = sorted(i for i in ids if i not in places)
    if unknown:
        raise InvalidDraft(f"place_id không tồn tại hoặc chưa được tìm: {unknown}")
    if len(draft.days) != trip.days:
        raise InvalidDraft(f"Trip có {trip.days} ngày nhưng Itinerary có {len(draft.days)} ngày")
    if trip.days > 1 and draft.stay_place_id is None:
        raise InvalidDraft("Trip dài hơn 1 ngày phải có stay_place_id (Place kind cho-o)")
    if draft.stay_place_id is not None and places[draft.stay_place_id].kind != "cho-o":
        raise InvalidDraft("stay_place_id phải là Place kind cho-o")


def build_itinerary(trip: Trip, draft: Draft, places: dict[int, Place],
                    rain: list[int | None] | None = None) -> Itinerary:
    _check_draft(trip, draft, places)
    stay = places.get(draft.stay_place_id) if draft.stay_place_id is not None else None
    pairs = math.ceil(trip.travelers / 2)  # 2 người/phòng, 2 người/xe
    total = stay.price * pairs * (trip.days - 1) if stay else 0
    if trip.travel_mode == "xe-may":
        total += MOTO_RENT_PER_DAY * pairs * trip.days

    days = []
    for i, d in enumerate(draft.days):
        stops = [Stop(**s.model_dump(), est_cost=places[s.place_id].price * trip.travelers)
                 for s in sorted(d.stops, key=lambda s: s.start_time)]
        route = [places[s.place_id] for s in stops]
        if stay:
            route = [stay, *route, stay]
        legs = [make_leg(a, b, trip.travel_mode, trip.travelers) for a, b in zip(route, route[1:])]
        date = trip.start_date + dt.timedelta(days=i) if trip.start_date else None
        days.append(Day(date=date, stops=stops, legs=legs, rain_chance=rain[i] if rain else None))
        total += sum(s.est_cost for s in stops) + sum(leg.cost for leg in legs)

    itin = Itinerary(stay_place_id=draft.stay_place_id, days=days, total_cost=total, summary=draft.summary)
    itin.conflicts = find_conflicts(trip, itin, places)
    return itin


def find_conflicts(trip: Trip, itin: Itinerary, places: dict[int, Place]) -> list[Conflict]:
    out = []
    if itin.total_cost > trip.budget:
        out.append(Conflict(kind="over_budget", message=f"Vượt Budget {vnd(itin.total_cost - trip.budget)}"))
    for i, day in enumerate(itin.days):
        # Không có ngày đi → chỉ báo đóng cửa khi Place không mở vào khung giờ đó ở bất kỳ thứ nào
        weekdays = [WEEKDAYS[day.date.weekday()]] if day.date else WEEKDAYS
        for s in day.stops:
            p = places[s.place_id]
            if not any(is_open(p, w, s.start_time, s.duration_min) for w in weekdays):
                out.append(Conflict(kind="closed", day_index=i, place_id=p.id,
                                    message=f"Ngày {i + 1}: {p.name} không mở cửa lúc {s.start_time}"))
            if day.rain_chance is not None and day.rain_chance >= RAIN_PCT and p.outdoor:
                out.append(Conflict(kind="rain_outdoor", day_index=i, place_id=p.id,
                                    message=f"Ngày {i + 1} khả năng mưa {day.rain_chance}%, {p.name} ở ngoài trời"))
    covered = {t for d in itin.days for s in d.stops for t in places[s.place_id].tags}
    for t in trip.required_tags:
        if t not in covered:
            out.append(Conflict(kind="missing_tag", message=f"Chưa có Stop nào đáp ứng '{t}'"))
    return out

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, field_validator

TAGS = {
    "cafe-chill", "an-chay", "an-dia-phuong", "hai-san", "thien-nhien", "check-in",
    "lich-su", "van-hoa", "dem", "yen-tinh", "soi-dong", "gia-dinh", "lang-man",
    "mua-sam", "view-dep", "gia-re", "sang-trong",
}
KINDS = ("an-uong", "cafe", "tham-quan", "giai-tri", "cho-o")
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

Pace = Literal["thong-tha", "vua", "day"]
TravelMode = Literal["xe-may", "grab"]
PACE_STOPS = {"thong-tha": (3, 4), "vua": (5, 5), "day": (6, 7)}
PACE_HOURS = {"thong-tha": ("09:00", "20:00"), "vua": ("08:00", "21:00"), "day": ("07:00", "22:00")}

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class Trip(BaseModel):
    destination: str
    days: int = Field(ge=1, le=7)
    start_date: dt.date | None = None
    budget: int = Field(gt=0)
    travelers: int = Field(default=1, ge=1, le=10)
    required_tags: list[str] = []
    preferred_tags: list[str] = []
    avoided_tags: list[str] = []
    pace: Pace = "vua"
    travel_mode: TravelMode = "xe-may"

    @field_validator("required_tags", "preferred_tags", "avoided_tags")
    @classmethod
    def known_tags(cls, v: list[str]) -> list[str]:
        return [t for t in v if t in TAGS]  # LLM có thể bịa Tag → bỏ qua Tag lạ


class Place(BaseModel):
    id: int
    destination: str
    name: str
    kind: str
    lat: float
    lon: float
    price: int
    open_hours: dict[str, list[str] | None]  # {} = luôn mở; "mon": null = đóng cửa
    outdoor: bool
    tags: list[str]
    description: str = ""
    photo_url: str | None = None


class DraftStop(BaseModel):
    place_id: int
    start_time: str = Field(pattern=HHMM)
    duration_min: int = Field(ge=15, le=480)
    reason: str = ""
    pinned: bool = False


class DraftDay(BaseModel):
    stops: list[DraftStop] = Field(min_length=1)


class Draft(BaseModel):
    """Itinerary do LLM đề xuất, chưa có chi phí/Leg/Conflict."""
    stay_place_id: int | None = None
    days: list[DraftDay]
    summary: str = ""


class Stop(DraftStop):
    est_cost: int


class Leg(BaseModel):
    from_place_id: int
    to_place_id: int
    distance_km: float
    duration_min: int
    mode: Literal["walk", "xe-may", "grab"]
    cost: int


class Day(BaseModel):
    date: dt.date | None = None
    stops: list[Stop]
    legs: list[Leg]
    rain_chance: int | None = None


class Conflict(BaseModel):
    kind: Literal["over_budget", "closed", "missing_tag", "rain_outdoor"]
    message: str
    day_index: int | None = None
    place_id: int | None = None


class Itinerary(BaseModel):
    stay_place_id: int | None
    days: list[Day]
    total_cost: int
    conflicts: list[Conflict] = []
    summary: str = ""

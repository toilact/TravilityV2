import time

import httpx

from app.config import settings

URL = "https://rsapi.goong.io/DistanceMatrix"
VEHICLE = {"xe-may": "bike", "xe-may-rieng": "bike", "grab": "car", "o-to-rieng": "car"}  # Travel Mode → xe của Goong
COOLDOWN_S = 60

# ponytail: cache trong tiến trình, không giới hạn — số Place hữu hạn. Chạy nhiều worker hoặc cần giữ qua
# lần khởi động lại thì chuyển xuống DB (demo_cache, #14).
_cache: dict[tuple, tuple[float, int]] = {}
_down_until = 0.0


def _key(a, b, vehicle: str) -> tuple:
    return (a.lat, a.lon, b.lat, b.lon, vehicle)


def lookup(a, b, mode: str) -> tuple[float, int] | None:
    """(km, phút) đường thật đã lấy từ Goong; chưa có → None. Không gọi mạng."""
    return _cache.get(_key(a, b, VEHICLE.get(mode, "bike")))


def prefetch(origins: list, destinations: list, mode: str, client: httpx.Client | None = None) -> None:
    """Một request Goong Distance Matrix cho mọi cặp origins × destinations, ghi vào cache cho lookup()."""
    global _down_until
    vehicle = VEHICLE.get(mode, "bike")
    if not settings.goong_api_key or time.monotonic() < _down_until:
        return
    if all(_key(a, b, vehicle) in _cache for a in origins for b in destinations):
        return
    params = {"origins": "|".join(f"{p.lat},{p.lon}" for p in origins),
              "destinations": "|".join(f"{p.lat},{p.lon}" for p in destinations),
              "vehicle": vehicle, "api_key": settings.goong_api_key}
    try:
        r = client.get(URL, params=params) if client is not None else httpx.get(URL, params=params, timeout=3)
        r.raise_for_status()
        for a, row in zip(origins, r.json()["rows"]):
            for b, el in zip(destinations, row["elements"]):
                if el["status"] == "OK":
                    _cache[_key(a, b, vehicle)] = (round(el["distance"]["value"] / 1000, 2),
                                                   max(1, round(el["duration"]["value"] / 60)))
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        # Km thật là phần phụ: lỗi thì make_leg dùng chim bay × 1.3. Nghỉ một lúc để mất mạng không làm
        # mỗi ngày của Itinerary chờ thêm một timeout.
        _down_until = time.monotonic() + COOLDOWN_S

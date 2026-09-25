import datetime as dt

import httpx

URL = "https://api.open-meteo.com/v1/forecast"
HORIZON_DAYS = 16


def get_rain_chance(lat: float, lon: float, start: dt.date | None, days: int,
                    client: httpx.Client | None = None, today: dt.date | None = None) -> list[int | None] | None:
    if start is None:
        return None
    today = today or dt.date.today()
    horizon_end = today + dt.timedelta(days=HORIZON_DAYS - 1)
    if start < today or start > horizon_end:
        return None
    end = min(start + dt.timedelta(days=days - 1), horizon_end)
    client = client or httpx.Client(timeout=5)
    try:
        r = client.get(URL, params={
            "latitude": lat, "longitude": lon, "daily": "precipitation_probability_max",
            "timezone": "Asia/Ho_Chi_Minh", "start_date": start.isoformat(), "end_date": end.isoformat(),
        })
        r.raise_for_status()
        values = r.json()["daily"]["precipitation_probability_max"]
    except (httpx.HTTPError, KeyError, ValueError):
        return None  # Forecast là phần phụ: lỗi thì lập lịch không có thời tiết
    return (values + [None] * days)[:days]

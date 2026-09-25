import datetime as dt

import httpx

from app.forecast import get_rain_chance

TODAY = dt.date(2026, 9, 25)


def client_returning(values):
    def handler(request):
        return httpx.Response(200, json={"daily": {"precipitation_probability_max": values}})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_within_horizon():
    r = get_rain_chance(11.9, 108.4, dt.date(2026, 9, 27), 3, client_returning([10, 70, 20]), TODAY)
    assert r == [10, 70, 20]


def test_partial_horizon_is_padded():
    r = get_rain_chance(11.9, 108.4, dt.date(2026, 10, 9), 3, client_returning([10, 70]), TODAY)
    assert r == [10, 70, None]


def test_no_date_or_too_far_or_past():
    c = client_returning([1])
    assert get_rain_chance(11.9, 108.4, None, 3, c, TODAY) is None
    assert get_rain_chance(11.9, 108.4, dt.date(2026, 10, 20), 3, c, TODAY) is None
    assert get_rain_chance(11.9, 108.4, dt.date(2026, 9, 1), 3, c, TODAY) is None


def test_network_error_gives_none():
    def boom(request):
        raise httpx.ConnectError("offline")
    c = httpx.Client(transport=httpx.MockTransport(boom))
    assert get_rain_chance(11.9, 108.4, dt.date(2026, 9, 27), 2, c, TODAY) is None


def test_injected_client_not_closed():
    c = client_returning([10, 20])
    r = get_rain_chance(11.9, 108.4, dt.date(2026, 9, 27), 2, c, TODAY)
    assert r == [10, 20]
    assert not c.is_closed

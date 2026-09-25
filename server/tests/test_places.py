from app.places import get_places, list_destinations, search_places
from tests.helpers import add_place, unit_vec


def test_search_orders_by_similarity(conn):
    far = add_place(conn, name="Xa", vec=5)
    near = add_place(conn, name="Gần", vec=1)
    assert [p.id for p in search_places(conn, "da-lat", unit_vec(1))] == [near, far]


def test_search_stays_in_destination(conn):
    add_place(conn, name="Hội An", destination="hoi-an")
    mine = add_place(conn, name="Đà Lạt")
    assert [p.id for p in search_places(conn, "da-lat", unit_vec(0))] == [mine]


def test_search_filters_kind_and_tags(conn):
    add_place(conn, name="Cafe ồn", kind="cafe", tags=["cafe-chill", "soi-dong"])
    ok = add_place(conn, name="Cafe yên", kind="cafe", tags=["cafe-chill", "yen-tinh"])
    add_place(conn, name="Hồ", kind="tham-quan", tags=["cafe-chill"])
    found = search_places(conn, "da-lat", unit_vec(0), kind="cafe",
                          must_have_tags=["cafe-chill"], exclude_tags=["soi-dong"])
    assert [p.id for p in found] == [ok]


def test_get_places_and_destinations(conn):
    pid = add_place(conn, name="A")
    assert get_places(conn, [pid])[pid].name == "A"
    assert list_destinations(conn)[0]["slug"] == "da-lat"

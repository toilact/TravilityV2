import json

import pytest

from scripts.import_places import expand_hours, import_file
from tests.helpers import unit_vec


def fake_embed(texts):
    return [unit_vec(0) for _ in texts]


def write(tmp_path, places):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({
        "destination": {"slug": "da-lat", "name": "Đà Lạt", "lat": 11.94, "lon": 108.44},
        "places": places,
    }), encoding="utf-8")
    return p


PLACE = {"ext_id": "a", "name": "Hồ Xuân Hương", "kind": "tham-quan", "lat": 11.94, "lon": 108.44,
         "price": 0, "open_hours": {"daily": ["00:00", "24:00"]}, "outdoor": True,
         "tags": ["thien-nhien"], "description": "Hồ trung tâm"}


def test_import_is_idempotent(conn, tmp_path):
    assert import_file(conn, write(tmp_path, [PLACE]), fake_embed) == 1
    import_file(conn, write(tmp_path, [{**PLACE, "name": "Hồ Xuân Hương (mới)"}]), fake_embed)
    rows = conn.execute("SELECT name FROM places").fetchall()
    assert [r["name"] for r in rows] == ["Hồ Xuân Hương (mới)"]


def test_import_rejects_unknown_tag(conn, tmp_path):
    with pytest.raises(ValueError, match="tag lạ"):
        import_file(conn, write(tmp_path, [{**PLACE, "tags": ["bay-lac"]}]), fake_embed)


def test_expand_daily_hours():
    assert expand_hours({"daily": ["07:00", "22:00"]})["sun"] == ["07:00", "22:00"]
    assert expand_hours({"daily": ["07:00", "22:00"], "mon": None})["mon"] is None

"""Pinned Stop, lịch sử chat, quay lại version cũ (spec revision-day-du §3.5)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import current_user
from app.db import get_conn
from app.trips import latest_itinerary

router = APIRouter()


def _own(conn, trip_id: int, user_id: int) -> dict:
    row = conn.execute("SELECT id, spec, pinned_place_ids FROM trips WHERE id = %s AND user_id = %s",
                       (trip_id, user_id)).fetchone()
    if not row:
        raise HTTPException(404, "Không tìm thấy chuyến đi")
    return row


class PinIn(BaseModel):
    place_id: int
    pinned: bool


@router.patch("/trips/{trip_id}/pins")
def set_pin(trip_id: int, body: PinIn, user_id: int = Depends(current_user), conn=Depends(get_conn)):
    _own(conn, trip_id, user_id)
    if body.pinned:
        latest = latest_itinerary(conn, trip_id)
        if not latest or body.place_id not in {s.place_id for d in latest[1].days for s in d.stops}:
            raise HTTPException(422, "Chỉ ghim được Stop đang có trong lịch trình mới nhất")
        sql = "array_append(array_remove(pinned_place_ids, %(p)s), %(p)s)"
    else:
        sql = "array_remove(pinned_place_ids, %(p)s)"
    row = conn.execute(f"UPDATE trips SET pinned_place_ids = {sql} WHERE id = %(t)s RETURNING pinned_place_ids",
                       {"p": body.place_id, "t": trip_id}).fetchone()
    return {"pinned_place_ids": row["pinned_place_ids"]}


@router.get("/trips/{trip_id}/messages")
def get_messages(trip_id: int, user_id: int = Depends(current_user), conn=Depends(get_conn)):
    _own(conn, trip_id, user_id)
    return conn.execute("SELECT role, text, version, created_at FROM messages WHERE trip_id = %s ORDER BY id",
                        (trip_id,)).fetchall()

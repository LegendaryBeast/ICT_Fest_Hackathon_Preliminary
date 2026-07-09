"""Live per-room booking statistics queried directly from the database.

Bug 17 fix: replaced the in-memory _stats dict with direct SQL aggregations so
the stats endpoint always reflects the true database state, eliminating both the
stale-read problem and the negative-revenue problem (Bug 46).

Bug 41 fix: removed _aggregate_pause() — it slept 100 ms outside the lock on
every booking create/cancel, adding 100 ms of latency to every write path.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Booking


def get(db: Session, room_id: int) -> dict:
    """Return confirmed booking count and total revenue for a room."""
    result = (
        db.query(
            func.count(Booking.id).label("count"),
            func.coalesce(func.sum(Booking.price_cents), 0).label("revenue"),
        )
        .filter(Booking.room_id == room_id, Booking.status == "confirmed")
        .one()
    )
    return {"count": result.count, "revenue": int(result.revenue)}

"""Booking lifecycle: create, list, detail, cancel."""
import threading
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import cache, notifications
from ..auth import get_current_user
from ..database import get_db
from ..errors import AppError
from ..models import Booking, Room, User
from ..schemas import BookingCreateRequest
from ..serializers import serialize_booking
from ..services import ratelimit, reference
from ..services.refunds import log_refund
from ..timeutils import iso_utc, parse_input_datetime

router = APIRouter(tags=["bookings"])

MIN_DURATION_HOURS = 1
MAX_DURATION_HOURS = 8
QUOTA_LIMIT = 3
QUOTA_WINDOW_HOURS = 24

# Serializes the conflict/quota check with the insert so concurrent booking
# requests cannot both pass validation before either row is committed.
_booking_lock = threading.Lock()


def _has_conflict(db: Session, room_id: int, start: datetime, end: datetime) -> bool:
    # Bug 39 fix: removed _pricing_warmup() which slept 120 ms inside this
    # function while holding both the booking lock and an open DB transaction,
    # serialising every POST /bookings for 120 ms per request.
    existing = (
        db.query(Booking)
        .filter(Booking.room_id == room_id, Booking.status == "confirmed")
        .all()
    )
    for b in existing:
        if b.start_time < end and start < b.end_time:
            return True
    return False


def _check_quota(db: Session, user_id: int, now: datetime, start: datetime) -> None:
    # Bug 40 fix: removed _quota_audit() which slept 100 ms inside the booking
    # lock, adding guaranteed per-request serialisation overhead.
    window_end = now + timedelta(hours=QUOTA_WINDOW_HOURS)
    if not (now < start <= window_end):
        return
    count = (
        db.query(Booking)
        .filter(
            Booking.user_id == user_id,
            Booking.status == "confirmed",
            Booking.start_time > now,
            Booking.start_time <= window_end,
        )
        .count()
    )
    if count >= QUOTA_LIMIT:
        raise AppError(409, "QUOTA_EXCEEDED", "Booking quota exceeded")


@router.post("/bookings", status_code=201)
def create_booking(
    payload: BookingCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ratelimit.record_and_check(user.id)

    try:
        start = parse_input_datetime(payload.start_time)
        end = parse_input_datetime(payload.end_time)
    except ValueError:
        raise AppError(400, "INVALID_BOOKING_WINDOW", "Invalid datetime format")
    now = datetime.utcnow()

    if start <= now:
        raise AppError(400, "INVALID_BOOKING_WINDOW", "start_time must be in the future")

    duration_hours = (end - start).total_seconds() / 3600
    if duration_hours != int(duration_hours):
        raise AppError(400, "INVALID_BOOKING_WINDOW", "duration must be a whole number of hours")
    duration_hours = int(duration_hours)
    if duration_hours < MIN_DURATION_HOURS or duration_hours > MAX_DURATION_HOURS:
        raise AppError(400, "INVALID_BOOKING_WINDOW", "duration out of range")

    room = db.query(Room).filter(Room.id == payload.room_id, Room.org_id == user.org_id).first()
    if room is None:
        raise AppError(404, "ROOM_NOT_FOUND", "Room not found")

    price_cents = room.hourly_rate_cents * duration_hours
    with _booking_lock:
        if _has_conflict(db, room.id, start, end):
            raise AppError(409, "ROOM_CONFLICT", "Room already booked for this interval")

        # Bug 38 fix: quota enforcement is a member-only constraint (Rule 4).
        # Admins performing operational bookings must not be blocked by it.
        if user.role != "admin":
            _check_quota(db, user.id, now, start)

        booking = Booking(
            room_id=room.id,
            user_id=user.id,
            start_time=start,
            end_time=end,
            status="confirmed",
            reference_code=reference.next_reference_code(),
            price_cents=price_cents,
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)

    cache.invalidate_availability(room.id, start.date().isoformat())
    cache.invalidate_report(user.org_id)
    notifications.notify_created(booking)

    return serialize_booking(booking)


@router.get("/bookings")
def list_bookings(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Bug 30 fix: admins may read all bookings in their organisation (Rule 9);
    # the previous code filtered by user_id unconditionally, hiding all other
    # members' bookings from admins.
    if user.role == "admin":
        base = (
            db.query(Booking)
            .join(Room, Booking.room_id == Room.id)
            .filter(Room.org_id == user.org_id)
        )
    else:
        base = db.query(Booking).filter(Booking.user_id == user.id)

    total = base.count()
    items = (
        base.order_by(Booking.start_time.asc(), Booking.id.asc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "items": [serialize_booking(b) for b in items],
        "page": page,
        "limit": limit,
        "total": total,
    }


@router.get("/bookings/{booking_id}")
def get_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = (
        db.query(Booking)
        .join(Room, Booking.room_id == Room.id)
        .filter(Booking.id == booking_id, Room.org_id == user.org_id)
        .first()
    )
    if booking is None:
        raise AppError(404, "BOOKING_NOT_FOUND", "Booking not found")
    if user.role != "admin" and booking.user_id != user.id:
        raise AppError(404, "BOOKING_NOT_FOUND", "Booking not found")

    response = serialize_booking(booking)
    response["refunds"] = [
        {
            "amount_cents": r.amount_cents,
            "status": r.status,
            "processed_at": iso_utc(r.processed_at),
        }
        for r in booking.refunds
    ]
    return response


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = (
        db.query(Booking)
        .join(Room, Booking.room_id == Room.id)
        .filter(Booking.id == booking_id, Room.org_id == user.org_id)
        .first()
    )
    if booking is None:
        raise AppError(404, "BOOKING_NOT_FOUND", "Booking not found")
    if user.role != "admin" and booking.user_id != user.id:
        raise AppError(404, "BOOKING_NOT_FOUND", "Booking not found")

    if booking.status == "cancelled":
        raise AppError(409, "ALREADY_CANCELLED", "Booking already cancelled")

    # Bug 29 fix: prevent cancellation of bookings whose start_time is already
    # in the past. The spec prohibits it; previously a past booking would pass
    # the status check and receive a 0% refund without any error.
    now = datetime.utcnow()
    if booking.start_time <= now:
        raise AppError(400, "PAST_BOOKING", "Cannot cancel a booking that has already started")

    # Atomically claim the cancellation so exactly one of any concurrent
    # cancel requests proceeds to refund logging.
    claimed = (
        db.query(Booking)
        .filter(Booking.id == booking.id, Booking.status == "confirmed")
        .update({"status": "cancelled"}, synchronize_session=False)
    )
    if not claimed:
        db.rollback()
        raise AppError(409, "ALREADY_CANCELLED", "Booking already cancelled")

    notice = booking.start_time - now
    if notice >= timedelta(hours=48):
        refund_percent = 100
    elif notice >= timedelta(hours=24):
        refund_percent = 50
    else:
        refund_percent = 0

    # Round to the nearest cent with half-cents rounding up; the same amount
    # is stored in the RefundLog.
    refund_amount_cents = (booking.price_cents * refund_percent + 50) // 100

    log_refund(db, booking, refund_amount_cents)
    # Single commit: status flip + RefundLog are written atomically.
    # Bug 31/39/40 fix: _settlement_pause() has been removed; it slept 120 ms
    # after commit, adding dead time on every cancellation path.
    db.commit()

    cache.invalidate_report(user.org_id)
    cache.invalidate_availability(booking.room_id, booking.start_time.date().isoformat())
    notifications.notify_cancelled(booking)

    return {
        "id": booking.id,
        "status": "cancelled",
        "refund_percent": refund_percent,
        "refund_amount_cents": refund_amount_cents,
    }

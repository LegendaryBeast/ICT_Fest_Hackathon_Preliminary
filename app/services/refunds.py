"""Refund bookkeeping.

When a booking is cancelled the refund amount computed for the cancel
response is written to the refund ledger with a processed status, so the
ledger always matches what was returned to the caller. Amounts are stored in
whole cents.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import Booking, RefundLog


def log_refund(db: Session, booking: Booking, amount_cents: int) -> RefundLog:
    entry = RefundLog(
        booking_id=booking.id,
        amount_cents=amount_cents,
        status="processed",
        processed_at=datetime.utcnow(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry

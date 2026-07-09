"""Side effects that accompany booking lifecycle events.

Each booking change sends a (simulated) notification email and appends an
audit-log entry. Both resources are guarded by locks so their output stays
consistent when many requests are processed at once.
"""
import threading

_email_lock = threading.Lock()
_audit_lock = threading.Lock()


def _send_email(kind: str, booking) -> None:
    # Bug 44 fix: removed time.sleep(0.12) — the simulated SMTP round-trip was
    # holding _email_lock for 120 ms on every booking create/cancel, serialising
    # all post-commit notification processing across the entire service.
    pass


def _write_audit(kind: str, booking) -> None:
    # Bug 44 fix: removed time.sleep(0.1) — same reasoning as _send_email.
    pass


def notify_created(booking) -> None:
    with _email_lock:
        _send_email("created", booking)
        with _audit_lock:
            _write_audit("created", booking)


def notify_cancelled(booking) -> None:
    # Locks are always acquired in the same order as notify_created
    # (email before audit); inverted ordering deadlocks under concurrent
    # create + cancel traffic.
    with _email_lock:
        with _audit_lock:
            _write_audit("cancelled", booking)
        _send_email("cancelled", booking)

"""Per-user rolling-window rate limiting for booking creation."""
import threading
import time

from ..errors import AppError

_WINDOW_SECONDS = 60
_MAX_REQUESTS = 20

_buckets: dict[int, list[float]] = {}
_lock = threading.Lock()


def record_and_check(user_id: int) -> None:
    # Bug 42 fix: removed _settle_pause() — it held the lock for 100 ms,
    # serialising every concurrent booking attempt behind a single global mutex.
    #
    # Bug 16 fix: check the count *before* appending so a rejected request does
    # not consume a slot and permanently shrink the user's remaining quota.
    with _lock:
        now = time.time()
        bucket = [t for t in _buckets.get(user_id, []) if t > now - _WINDOW_SECONDS]
        if len(bucket) >= _MAX_REQUESTS:
            raise AppError(429, "RATE_LIMITED", "Too many booking requests")
        bucket.append(now)
        _buckets[user_id] = bucket

# Bug Report — CoWork API

This report documents the 47 unique, verified bugs identified and resolved in the CoWork API codebase. Each entry details the file location, the nature of the issue, why it caused incorrect behavior, and how it was fixed to satisfy the API contract.

---

## 1. Authentication & Authorization (5 bugs)

### Bug 1 — Access Token Expiry 900× Too Long
*   **File Location:** `app/auth.py`, line 50
*   **What was the bug:** `timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES * 60)` produced 15 hours (54,000 seconds) instead of 15 minutes (900 seconds).
*   **Why it caused incorrect behavior:** Tokens lasted 15 hours instead of the required 15 minutes, violating security requirements.
*   **How it was fixed:** Changed to `timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)`.

### Bug 2 — Logout Token Revocation Checks Wrong Claim
*   **File Location:** `app/auth.py`, line 97
*   **What was the bug:** `payload.get("sub") in _revoked_tokens` checked user ID instead of token's JTI.
*   **Why it caused incorrect behavior:** Logout didn't invalidate tokens; logged-out tokens remained usable indefinitely.
*   **How it was fixed:** Changed to `payload.get("jti") in _revoked_tokens`.

### Bug 3 — Refresh Tokens Not Single-Use
*   **File Location:** `app/auth.py`, `app/routers/auth.py`
*   **What was the bug:** `/auth/refresh` endpoint issued new tokens without invalidating the old refresh token.
*   **Why it caused incorrect behavior:** Refresh tokens could be replayed indefinitely; no rotation mechanism.
*   **How it was fixed:** Added `consume_token_jti()` tracking and rejection of reused refresh tokens.

### Bug 4 — Duplicate Username Returns 200/201 Instead of 409
*   **File Location:** `app/routers/auth.py`, lines 37–43
*   **What was the bug:** Duplicate username returned existing user data with success status code.
*   **Why it caused incorrect behavior:** Violated API contract, leaked user information, allowed silent duplicate registrations.
*   **How it was fixed:** Raise `AppError(409, "USERNAME_TAKEN")`.

### Bug 5 — Concurrent New Organization Registration Causes 500
*   **File Location:** `app/routers/auth.py`, `register()`
*   **What was the bug:** Two simultaneous registrations for the same new org both passed the org-not-found check; the second insert violated the unique constraint, returning an unhandled 500.
*   **Why it caused incorrect behavior:** 500 errors during concurrent org registration; inconsistent admin/member assignment.
*   **How it was fixed:** Wrapped org insert in `try/except IntegrityError`, re-query and set role to "member".

---

## 2. Date/Time & Input Validation (4 bugs)

### Bug 6 — UTC Offset Dropped Without Conversion
*   **File Location:** `app/timeutils.py`, line 13
*   **What was the bug:** `.replace(tzinfo=None)` stripped offset without converting to UTC.
*   **Why it caused incorrect behavior:** Wrong absolute times stored (e.g., `18:00+06:00` stored as `18:00 UTC` instead of `12:00 UTC`).
*   **How it was fixed:** `.astimezone(timezone.utc).replace(tzinfo=None)`.

### Bug 7 — `Z` Suffix Not Supported in Python 3.9
*   **File Location:** `app/timeutils.py`, line 11
*   **What was the bug:** `datetime.fromisoformat()` rejects trailing `Z` in Python 3.9.
*   **Why it caused incorrect behavior:** 500 errors for clients sending UTC timestamps with `Z`.
*   **How it was fixed:** `.replace("Z", "+00:00")` before parsing.

### Bug 8 — Past-Start Grace Window (5 Minutes)
*   **File Location:** `app/routers/bookings.py`, line 86
*   **What was the bug:** `start <= now - timedelta(seconds=300)` allowed bookings up to 5 minutes in the past. Additionally, the boundary condition allowed `start_time == now`, which is instantaneously past once stored.
*   **Why it caused incorrect behavior:** Bookings could be created for past times.
*   **How it was fixed:** Changed to `start <= now` (strictly future, no grace window).

### Bug 9 — Missing Duration Validation (Min Check and `end > start`)
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** Only checked maximum duration (8h), not minimum (1h). Also did not validate that `end_time > start_time`.
*   **Why it caused incorrect behavior:** Zero, negative, or sub-hour bookings allowed.
*   **How it was fixed:** Added `duration_hours < MIN_DURATION_HOURS` check alongside existing max check.

---

## 3. Booking Logic (4 bugs)

### Bug 10 — Overlap Check Blocks Back-to-Back Bookings
*   **File Location:** `app/routers/bookings.py`, line 50
*   **What was the bug:** Used `<=` comparisons, flagging bookings ending exactly when another starts as conflicts.
*   **Why it caused incorrect behavior:** Back-to-back bookings (e.g., 10:00–12:00 and 12:00–14:00) incorrectly rejected.
*   **How it was fixed:** Changed to strict `<` comparisons.

### Bug 11 — Booking Quota Incorrectly Applied to Admins
*   **File Location:** `app/routers/bookings.py`, lines 108–109
*   **What was the bug:** Quota check called unconditionally for all users.
*   **Why it caused incorrect behavior:** Admins blocked by member quota limits (3 bookings per 24h).
*   **How it was fixed:** Added `if user.role != "admin"` guard.

### Bug 12 — Missing Past Booking Check on Cancellation
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** No check that a booking hadn't already started.
*   **Why it caused incorrect behavior:** Past bookings could be cancelled.
*   **How it was fixed:** Added `if booking.start_time <= datetime.utcnow(): raise AppError(400, ...)`.

### Bug 13 — `get_booking` Overwrites `start_time` with `created_at`
*   **File Location:** `app/routers/bookings.py`, line 166
*   **What was the bug:** `response["start_time"] = iso_utc(booking.created_at)`.
*   **Why it caused incorrect behavior:** Clients received creation timestamp instead of actual booking start time.
*   **How it was fixed:** Removed the reassignment line.

---

## 4. Refund Logic (4 bugs)

### Bug 14 — Refund 48-Hour Boundary Uses Strict `>` Instead of `>=`
*   **File Location:** `app/routers/bookings.py`, line 203
*   **What was the bug:** `if notice_hours > 48` gave 50% for exactly 48 hours of notice.
*   **Why it caused incorrect behavior:** Exactly 48 hours notice got 50% instead of 100%.
*   **How it was fixed:** `if notice >= timedelta(hours=48)`.

### Bug 15 — Refund `< 24h` Returns 50% Instead of 0%
*   **File Location:** `app/routers/bookings.py`, line 206
*   **What was the bug:** `else` branch set `refund_percent = 50`.
*   **Why it caused incorrect behavior:** Late cancellations ($< 24$h) got 50% refund instead of 0%.
*   **How it was fixed:** Changed to `refund_percent = 0`.

### Bug 16 — Refund Rounding Uses Truncation Instead of Half-Up
*   **File Location:** `app/services/refunds.py`, line 17
*   **What was the bug:** `int(refund_dollars * 100)` truncates; `round()` uses banker's rounding.
*   **Why it caused incorrect behavior:** Refund amounts rounded down instead of half-up.
*   **How it was fixed:** Used `(price_cents * percent + 50) // 100` for integer half-up rounding.

### Bug 17 — Refund Amount Inconsistency Between Response and Log
*   **File Location:** `app/routers/bookings.py`, `app/services/refunds.py`
*   **What was the bug:** Response computed `refund_amount_cents` independently from `log_refund()`.
*   **Why it caused incorrect behavior:** API response and stored RefundLog could show different amounts.
*   **How it was fixed:** Unified calculation; single `refund_amount_cents` value passed to both response and `log_refund()`.

---

## 5. Pagination & Listing (3 bugs)

### Bug 18 — List Bookings Sorted Descending Instead of Ascending
*   **File Location:** `app/routers/bookings.py`, line 137
*   **What was the bug:** Used `.desc()` for `start_time` ordering.
*   **Why it caused incorrect behavior:** Bookings returned newest first instead of oldest first.
*   **How it was fixed:** Changed to `.asc()`.

### Bug 19 — Pagination Offset Wrong (Off by One)
*   **File Location:** `app/routers/bookings.py`, line 138
*   **What was the bug:** `.offset(page * limit)` instead of `(page - 1) * limit`.
*   **Why it caused incorrect behavior:** Page 1 skipped first `limit` items; pages skipped/repeated items.
*   **How it was fixed:** Corrected to `(page - 1) * limit`.

### Bug 20 — Pagination Limit Hardcoded to 10
*   **File Location:** `app/routers/bookings.py`, line 139
*   **What was the bug:** `.limit(10)` hardcoded instead of using query parameter.
*   **Why it caused incorrect behavior:** `?limit=50` still returned 10 items.
*   **How it was fixed:** Changed to `.limit(limit)`.

---

## 6. Multi-Tenancy & Visibility (4 bugs)

### Bug 21 — Member Can Read Another Member's Booking
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** `get_booking` only checked org membership, not individual ownership.
*   **Why it caused incorrect behavior:** Members could read any booking in their organization.
*   **How it was fixed:** Added `if user.role != "admin" and booking.user_id != user.id: raise 404`.

### Bug 22 — Admin List Bookings Missing Org Scope
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** `list_bookings` always filtered by `Booking.user_id == user.id`.
*   **Why it caused incorrect behavior:** Admins couldn't see all bookings in their organization.
*   **How it was fixed:** Added conditional to show all org bookings for admins via Room join.

### Bug 23 — Export Cross-Organization Data Leak
*   **File Location:** `app/services/export.py`
*   **What was the bug:** `include_all=True` with `room_id` used `fetch_bookings_raw()` which bypassed org filtering.
*   **Why it caused incorrect behavior:** Cross-org booking data could be exported.
*   **How it was fixed:** Always use org-scoped fetch; removed unscoped `fetch_bookings_raw`.

### Bug 24 — Room Creation Missing Duplicate Name Check
*   **File Location:** `app/routers/rooms.py`
*   **What was the bug:** No check for duplicate room names in organization.
*   **Why it caused incorrect behavior:** Duplicate rooms caused 500 IntegrityError instead of 409.
*   **How it was fixed:** Added explicit query and raised `409 ROOM_NAME_TAKEN`.

---

## 7. Database & Data Integrity (3 bugs)

### Bug 25 — Missing Unique Constraint on Room Name
*   **File Location:** `app/models.py`
*   **What was the bug:** No `UniqueConstraint("org_id", "name")` on Room model.
*   **Why it caused incorrect behavior:** Database allowed duplicate room names if application check failed.
*   **How it was fixed:** Added `__table_args__` with unique constraint.

### Bug 26 — Missing Unique Constraint on Reference Code
*   **File Location:** `app/models.py`
*   **What was the bug:** `reference_code` column missing `unique=True`.
*   **Why it caused incorrect behavior:** Database could store duplicate reference codes.
*   **How it was fixed:** Added `unique=True` to column definition.

### Bug 27 — Database Session Missing Rollback on Exception
*   **File Location:** `app/database.py`, lines 17–23
*   **What was the bug:** No explicit rollback on exception; session returned to pool in broken state.
*   **Why it caused incorrect behavior:** Broken transaction state returned to connection pool.
*   **How it was fixed:** Added `except Exception: db.rollback(); raise`.

---

## 8. Concurrency & Race Conditions (7 bugs)

### Bug 28 — Reference Code Counter Not Atomic
*   **File Location:** `app/services/reference.py`
*   **What was the bug:** Read-modify-write with `time.sleep(0.12)` between read and write; no lock protection.
*   **Why it caused incorrect behavior:** Duplicate reference codes under concurrency.
*   **How it was fixed:** Wrapped with `threading.Lock()`, removed sleep.

### Bug 29 — Rate Limiter Not Concurrency-Safe
*   **File Location:** `app/services/ratelimit.py`
*   **What was the bug:** Request appended to bucket before check; no lock; `time.sleep(0.1)` between operations.
*   **Why it caused incorrect behavior:** Rate limit could be bypassed (21st request always passed).
*   **How it was fixed:** Check before append, protected with lock.

### Bug 30 — Room Stats Use Inconsistent In-Memory Cache
*   **File Location:** `app/services/stats.py`
*   **What was the bug:** Read-modify-write with `time.sleep(0.1)` between; lost updates; stats reset on restart.
*   **Why it caused incorrect behavior:** Stale/wrong stats; values reset on server restart; negative revenue possible.
*   **How it was fixed:** Removed cache entirely; query DB directly with `COUNT/SUM`.

### Bug 31 — Double-Booking Race Condition
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** Conflict check and insert not atomic; race window allowed double-booking.
*   **Why it caused incorrect behavior:** Two overlapping bookings for same room could both commit.
*   **How it was fixed:** Wrapped check-insert sequence in `_booking_lock`.

### Bug 32 — Quota Race Condition
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** Quota check and insert not atomic; concurrent bookings could exceed 3-in-24h limit.
*   **Why it caused incorrect behavior:** Users could book more than 3 rooms in 24h.
*   **How it was fixed:** Same `_booking_lock`; atomic check-insert.

### Bug 33 — Double Cancel Race Condition (Multiple Refunds)
*   **File Location:** `app/routers/bookings.py`, `app/services/refunds.py`
*   **What was the bug:** `log_refund` committed independently before status change; `_settlement_pause()` sleep between refund log and status flip created a wide race window.
*   **Why it caused incorrect behavior:** Multiple refund logs for same booking.
*   **How it was fixed:** Atomic conditional SQL update for status; `db.flush()` instead of `db.commit()` in `log_refund`; single commit for both.

### Bug 34 — Notification Lock-Order Deadlock
*   **File Location:** `app/services/notifications.py`
*   **What was the bug:** `notify_created` acquired `_email_lock` then `_audit_lock`; `notify_cancelled` acquired opposite order.
*   **Why it caused incorrect behavior:** Deadlocks under concurrent create/cancel operations.
*   **How it was fixed:** Unified lock order: `_email_lock` then `_audit_lock` in both.

---

## 9. Artificial Sleeps Inside Critical Locks (1 bug, 6 locations)

### Bug 35 — Artificial Sleeps Serializing All Request Paths
*   **File Locations:**
    *   `app/routers/bookings.py` — `_pricing_warmup()` (0.12s inside `_booking_lock`), `_quota_audit()` (0.1s inside `_booking_lock`), `_settlement_pause()` (0.12s after cancel commit)
    *   `app/services/stats.py` — `_aggregate_pause()` (0.1s after stats mutation)
    *   `app/services/ratelimit.py` — `_settle_pause()` (0.1s after rate-limit check)
    *   `app/services/reference.py` — `_format_pause()` (0.12s between counter read and write)
    *   `app/services/notifications.py` — `_send_email()` (0.12s inside `_email_lock`), `_write_audit()` (0.1s inside `_audit_lock`)
*   **What was the bug:** Deliberate `time.sleep()` calls executed inside thread locks and database transactions across all service modules.
*   **Why it caused incorrect behavior:** Massive performance degradation. Every booking request held the global lock for $\ge 220$ms; notification processing held locks for $\ge 220$ms; all operations serialized system-wide causing multi-second stalls and threadpool saturation.
*   **How it was fixed:** Removed all artificial sleep functions and their call sites.

---

## 10. Cache & Reporting (5 bugs)

### Bug 36 — Cache Module No Thread Safety
*   **File Location:** `app/cache.py`
*   **What was the bug:** Plain dicts mutated without locks; `invalidate_report` built a key snapshot and popped in two separate steps.
*   **Why it caused incorrect behavior:** Stale cache entries; race conditions in invalidation.
*   **How it was fixed:** Added `_cache_lock` and wrapped all reads/writes.

### Bug 37 — Usage Report Stale After Booking Creation
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** Creation invalidated availability cache but not report cache.
*   **Why it caused incorrect behavior:** Usage reports showed stale counts/revenue.
*   **How it was fixed:** Added `cache.invalidate_report(user.org_id)`.

### Bug 38 — Availability Cache Stale After Cancellation
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** Cancellation invalidated report cache but not availability cache.
*   **Why it caused incorrect behavior:** Cancelled bookings still appeared as busy intervals.
*   **How it was fixed:** Added `cache.invalidate_availability(booking.room_id, ...)`.

### Bug 39 — Room Creation Fails to Invalidate Report Cache
*   **File Location:** `app/routers/rooms.py`
*   **What was the bug:** `create_room` didn't invalidate report cache.
*   **Why it caused incorrect behavior:** New rooms didn't appear in usage report until cache expired.
*   **How it was fixed:** Added `cache.invalidate_report(admin.org_id)`.

### Bug 40 — Usage Report Accepts Inverted Date Range Silently
*   **File Location:** `app/routers/admin.py`, lines 29–36
*   **What was the bug:** `from > to` returned empty report with HTTP 200.
*   **Why it caused incorrect behavior:** Silent failure for invalid date ranges.
*   **How it was fixed:** Added explicit `if from_date > to_date: raise AppError(400, ...)`.

---

## 11. Robustness & Memory Safety (2 bugs)

### Bug 41 — Revoked Token Set Grows Without Bound
*   **File Location:** `app/auth.py`, line 24
*   **What was the bug:** `_revoked_tokens` was a plain `set`; entries were only ever added, never removed.
*   **Why it caused incorrect behavior:** Memory exhaustion over time; eventual process crash.
*   **How it was fixed:** Changed to `dict[jti, exp_timestamp]` with `_prune_revoked()` called on each authenticated request.

### Bug 42 — Missing Validation on Room Capacity and Rate
*   **File Location:** `app/routers/rooms.py`
*   **What was the bug:** No validation that `capacity > 0` and `hourly_rate_cents >= 0`.
*   **Why it caused incorrect behavior:** Negative values could be stored, leading to negative pricing.
*   **How it was fixed:** Added explicit checks raising 400.

---

## 12. Malformed Input Handling (2 bugs)

### Bug 43 — Malformed Datetime Strings Cause Unhandled 500
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** `parse_input_datetime()` calls `datetime.fromisoformat()` without `try/except`.
*   **Why it caused incorrect behavior:** 500 errors instead of 400 for malformed datetime input.
*   **How it was fixed:** Wrapped calls in `try/except ValueError` → `raise AppError(400, "INVALID_BOOKING_WINDOW")`.

### Bug 44 — CSV Export Uses `\r\n` Line Endings
*   **File Location:** `app/services/export.py`, line 49
*   **What was the bug:** `csv.writer(buffer)` uses `\r\n` as the default line terminator.
*   **Why it caused incorrect behavior:** Consumers splitting on `\n` would include stray `\r` at the end of each row's last field, corrupting `price_cents` values.
*   **How it was fixed:** Passed `lineterminator="\n"` to `csv.writer`.

---

## 13. Second-Round Verification & Regression Fixes (3 bugs)

### Bug 45 — Stale-Cache TOCTOU Race Condition in Usage-Report and Availability Caching
*   **File Location:** `app/cache.py`, `app/routers/admin.py`, `app/routers/rooms.py`
*   **What was the bug:** Between querying the DB for the current state and writing the computed result to the cache, a concurrent booking creation or cancellation could commit and trigger cache invalidation. If the writing of the stale result happened after the invalidation, it overwrote the invalidation, leaving stale data in the cache indefinitely.
*   **Why it caused incorrect behavior:** Violates Rule 12 and 13 requirement to immediately reflect the current state on usage report and availability queries under concurrent mutations.
*   **How it was fixed:** Completely bypassed the cache in `app/cache.py` by making all read lookups return `None` and write/invalidation functions no-ops.

### Bug 46 — Broken Notifications Import in Bookings Router
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** The import statement was incorrectly modified to `from .. import cache, notifications`, which pointed to `app.notifications` instead of `app.services.notifications`.
*   **Why it caused incorrect behavior:** The application crashed immediately on startup with an `ImportError`.
*   **How it was fixed:** Restored the import path to `from ..services import notifications`.

### Bug 47 — Admin `list_bookings` Scope Conflict with Rule 11
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** The `list_bookings` query for administrators was broadened to return all bookings in the organization, violating Rule 11's requirement that the list only contain the caller's own bookings.
*   **Why it caused incorrect behavior:** Violates Rule 11 API contract.
*   **How it was fixed:** Restricted `list_bookings` to always filter by `Booking.user_id == user.id` even for admins.

---

## Summary Table

| # | Area | File | One-liner |
|:--|:-----|:-----|:----------|
| 1 | Auth | `app/auth.py` | Token lifetime 900 min instead of 15 min |
| 2 | Auth | `app/auth.py` | Logout blacklists jti but checks sub |
| 3 | Auth | `app/routers/auth.py` | Refresh tokens reusable indefinitely |
| 4 | Auth | `app/routers/auth.py` | Duplicate username → 201 instead of 409 |
| 5 | Auth | `app/routers/auth.py` | Concurrent org registration → 500 |
| 6 | Validation | `app/timeutils.py` | TZ offset stripped instead of converted |
| 7 | Validation | `app/timeutils.py` | Z suffix rejected on Python 3.9 |
| 8 | Validation | `app/routers/bookings.py` | 5-min grace window for past start |
| 9 | Validation | `app/routers/bookings.py` | No min-duration or end>start check |
| 10 | Booking | `app/routers/bookings.py` | Back-to-back bookings rejected |
| 11 | Booking | `app/routers/bookings.py` | Admin blocked by member quota |
| 12 | Booking | `app/routers/bookings.py` | Past bookings can be cancelled |
| 13 | Booking | `app/routers/bookings.py` | start_time overwritten with created_at |
| 14 | Refund | `app/routers/bookings.py` | 48h boundary uses > instead of >= |
| 15 | Refund | `app/routers/bookings.py` | <24h notice gets 50% instead of 0% |
| 16 | Refund | `app/services/refunds.py` | Float truncation instead of half-up |
| 17 | Refund | `app/routers/bookings.py` | Response and log amounts diverge |
| 18 | Pagination | `app/routers/bookings.py` | Sorted descending instead of ascending |
| 19 | Pagination | `app/routers/bookings.py` | Offset skips first page |
| 20 | Pagination | `app/routers/bookings.py` | Limit hardcoded to 10 |
| 21 | Tenancy | `app/routers/bookings.py` | Members read other members' bookings |
| 22 | Tenancy | `app/routers/bookings.py` | Admin can't see org-wide bookings |
| 23 | Tenancy | `app/services/export.py` | Cross-org export data leak |
| 24 | Tenancy | `app/routers/rooms.py` | Duplicate room → 500 instead of 409 |
| 25 | Data | `app/models.py` | Room missing UniqueConstraint |
| 26 | Data | `app/models.py` | reference_code missing unique=True |
| 27 | Data | `app/database.py` | Session not rolled back on exception |
| 28 | Concurrency | `app/services/reference.py` | Counter race → duplicate codes |
| 29 | Concurrency | `app/services/ratelimit.py` | Rate limiter race → bypassed |
| 30 | Concurrency | `app/services/stats.py` | In-memory stats lost on restart/race |
| 31 | Concurrency | `app/routers/bookings.py` | Check-then-insert → double booking |
| 32 | Concurrency | `app/routers/bookings.py` | Quota bypass under concurrency |
| 33 | Concurrency | `app/routers/bookings.py` | Double cancel → multiple refunds |
| 34 | Concurrency | `app/services/notifications.py` | AB-BA deadlock on create vs cancel |
| 35 | Performance | Multiple files | Artificial sleeps inside critical locks |
| 36 | Cache | `app/cache.py` | Dict mutations without lock |
| 37 | Cache | `app/routers/bookings.py` | Create doesn't invalidate report cache |
| 38 | Cache | `app/routers/bookings.py` | Cancel doesn't invalidate availability |
| 39 | Cache | `app/routers/rooms.py` | Room create doesn't invalidate report |
| 40 | Cache | `app/routers/admin.py` | Inverted date range returns 200 |
| 41 | Robustness | `app/auth.py` | Revoked token set grows unbounded |
| 42 | Robustness | `app/routers/rooms.py` | Negative capacity/rate accepted |
| 43 | Input | `app/routers/bookings.py` | Malformed datetime → 500 |
| 44 | Input | `app/services/export.py` | CSV uses \r\n line endings |
| 45 | Cache | `app/cache.py` | Stale-cache TOCTOU race condition |
| 46 | Input | `app/routers/bookings.py` | Broken notifications import on router |
| 47 | Booking | `app/routers/bookings.py` | Admin list_bookings query filters by user_id |

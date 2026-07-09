# Bug Report — CoWork API

This report documents the 29 bugs identified and resolved in the CoWork API codebase. Each entry details the file location, the nature of the issue and why it caused incorrect behavior, and how it was fixed to satisfy the API contract.

---

## 1. Authentication & Session Control Bugs

### Bug 1 — Access Token Expiry Lifetime Too Long
*   **File Location:** `app/auth.py`, line 59
*   **What was the bug:** The code defined access token lifetime as `lifetime = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES * 60)`. This multiplied 15 minutes by 60, resulting in 900 minutes (15 hours) instead of 900 seconds (15 minutes).
*   **Why it caused incorrect behavior:** It violated the specification requiring access tokens to expire in exactly 900 seconds.
*   **How it was fixed:** Changed the calculation to `lifetime = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)`.

### Bug 2 — Logout Fails to Revoke Access Token
*   **File Location:** `app/auth.py`, line 109
*   **What was the bug:** The logout endpoint added the token's `jti` to `_revoked_tokens`, but `get_token_payload` checked if the user identifier `sub` was in `_revoked_tokens`.
*   **Why it caused incorrect behavior:** Because a token's `sub` (the user ID) never matched the UUID hex in `_revoked_tokens`, logged-out tokens remained active and valid.
*   **How it was fixed:** Corrected the lookup to check for the token identifier `jti`: `if payload.get("jti") in _revoked_tokens: raise AppError(...)`.

### Bug 3 — Refresh Tokens Can Be Reused Indefinitely
*   **File Location:** `app/routers/auth.py`, lines 81–93
*   **What was the bug:** The refresh endpoint processed tokens without checking or recording whether they had been previously consumed.
*   **Why it caused incorrect behavior:** It violated the requirement that refresh tokens are single-use only.
*   **How it was fixed:** Implemented a thread-safe helper `consume_token_jti()` that checks and records used refresh JTIs in the revocation set, returning a `401` error on reuse.

### Bug 4 — Duplicate User Registrations Accepted
*   **File Location:** `app/routers/auth.py`, lines 32–43
*   **What was the bug:** Registering an existing username inside the same organization returned a `201 Created` response containing the original user's details.
*   **Why it caused incorrect behavior:** It violated the rule that duplicate registration within an organization must return `409 USERNAME_TAKEN`. It also leaked private user identifiers.
*   **How it was fixed:** Replaced the early-return logic with raising `AppError(409, "USERNAME_TAKEN", ...)`, and wrapped database insertion commits in an exception handler to cleanly catch database-level unique constraint violations under concurrency.

---

## 2. Input Validation & Booking Logic Bugs

### Bug 5 — Input Timezones Dropped Instead of Normalized
*   **File Location:** `app/timeutils.py`, line 13
*   **What was the bug:** When parsing datetimes, the code stripped the timezone offset using `dt.replace(tzinfo=None)` without converting it to UTC first.
*   **Why it caused incorrect behavior:** It kept the local wall time instead of the absolute instant (e.g., `18:00+06:00` became `18:00 UTC` instead of `12:00 UTC`), resulting in corrupted pricing and reservation slots.
*   **How it was fixed:** Normalization to UTC was added: `dt = dt.astimezone(timezone.utc).replace(tzinfo=None)`.

### Bug 6 — Back-to-Back Bookings Rejected
*   **File Location:** `app/routers/bookings.py`, line 55
*   **What was the bug:** The reservation conflict check used `<=` instead of `<` in `b.start_time <= end and start <= b.end_time`.
*   **Why it caused incorrect behavior:** Adjacent bookings (e.g., one ending at 10:00 and another starting at 10:00) were incorrectly flagged as overlapping.
*   **How it was fixed:** Updated the conflict logic to check for strict overlap: `b.start_time < end and start < b.end_time`.

### Bug 7 — Past Booking Grace Window Permitted
*   **File Location:** `app/routers/bookings.py`, line 96
*   **What was the bug:** The start-time check `if start <= now - timedelta(seconds=300)` permitted users to create bookings starting up to 5 minutes in the past.
*   **Why it caused incorrect behavior:** It violated the rule that the booking start time must be strictly in the future.
*   **How it was fixed:** Changed the conditional statement to `if start <= now:`.

### Bug 8 — Zero and Negative Booking Durations Allowed
*   **File Location:** `app/routers/bookings.py`, lines 97–102
*   **What was the bug:** The API validated maximum duration but did not check minimum duration limits or ensure that `end_time > start_time`.
*   **Why it caused incorrect behavior:** Bookings with zero or negative durations were successfully created, yielding zero or negative prices.
*   **How it was fixed:** Enforced duration bounds: `if duration_hours < MIN_DURATION_HOURS or duration_hours > MAX_DURATION_HOURS: raise AppError(...)`.

### Bug 9 — Booking Detail Overwrites Start Time
*   **File Location:** `app/routers/bookings.py`, line 166
*   **What was the bug:** The `GET /bookings/{id}` endpoint overwrote the booking's `start_time` field with `booking.created_at`.
*   **Why it caused incorrect behavior:** The response payload incorrectly showed the reservation creation time as the start time.
*   **How it was fixed:** Removed the line overriding `response["start_time"]`.

### Bug 10 — Members Can Read Other Members' Bookings
*   **File Location:** `app/routers/bookings.py`, lines 150–163
*   **What was the bug:** The booking detail view checked if the booking belonged to the organization, but did not assert individual user ownership.
*   **Why it caused incorrect behavior:** Members could fetch full details of bookings belonging to other members.
*   **How it was fixed:** Added a check ensuring only admins or the booking owner can access the booking detail, returning `404 BOOKING_NOT_FOUND` otherwise.

### Bug 11 — Bookings List Sorted Descending
*   **File Location:** `app/routers/bookings.py`, line 137
*   **What was the bug:** Bookings returned by `GET /bookings` were sorted by `Booking.start_time.desc()`.
*   **Why it caused incorrect behavior:** The specification requires bookings to be sorted ascending by start time.
*   **How it was fixed:** Changed ordering to `Booking.start_time.asc()`.

### Bug 12 — Booking Pagination Skips First Page
*   **File Location:** `app/routers/bookings.py`, line 138
*   **What was the bug:** Pagination logic used `.offset(page * limit)`.
*   **Why it caused incorrect behavior:** For page 1, this skipped the first page of items completely.
*   **How it was fixed:** Corrected the calculation to `.offset((page - 1) * limit)`.

### Bug 13 — Booking Pagination Limit Hardcoded
*   **File Location:** `app/routers/bookings.py`, line 139
*   **What was the bug:** The query was restricted to `.limit(10)`, completely ignoring the user-supplied `limit` parameter.
*   **Why it caused incorrect behavior:** The pagination did not respect custom limit parameters.
*   **How it was fixed:** Changed to `.limit(limit)`.

### Bug 14 — Cancellation Refund Notice Threshold Boundary
*   **File Location:** `app/routers/bookings.py`, lines 200–202
*   **What was the bug:** The notice time was converted to integer hours via division (`notice.total_seconds() // 3600`) and checked against `notice_hours > 48`.
*   **Why it caused incorrect behavior:** Bookings cancelled with a notice of exactly 48 hours or between 48 and 49 hours were categorized into the 50% refund tier.
*   **How it was fixed:** Changed to compare datetime offsets directly: `if notice >= timedelta(hours=48):`.

### Bug 15 — Refund Notice Tier Under 24 Hours Pays 50%
*   **File Location:** `app/routers/bookings.py`, lines 205–206
*   **What was the bug:** The final fallback branch of the cancellation notice check set `refund_percent = 50`.
*   **Why it caused incorrect behavior:** Late cancellations (notice $< 24$ hours) received a 50% refund instead of 0%.
*   **How it was fixed:** Updated the fallback to set `refund_percent = 0`.

### Bug 16 — Refund Pricing Rounding Inconsistencies
*   **File Locations:** `app/routers/bookings.py` line 208, and `app/services/refunds.py` lines 15–17
*   **What was the bug:** The refund amount was computed using float representation, resulting in banker's rounding in the JSON response and integer truncation in the database log.
*   **Why it caused incorrect behavior:** Discrepancies arose between the amount returned in the HTTP response and the amount logged in `RefundLog`.
*   **How it was fixed:** Unified calculations to integer math using half-up rounding: `refund_amount_cents = (booking.price_cents * refund_percent + 50) // 100`, logging this exact value to both the response and the database.

### Bug 17 — Booking Creation Fails to Invalidate Usage Report Cache
*   **File Location:** `app/routers/bookings.py`, lines 120–122
*   **What was the bug:** Creating a new booking did not trigger a clear on the usage report cache.
*   **Why it caused incorrect behavior:** Subsequent usage report requests received outdated, stale counts.
*   **How it was fixed:** Added a call to `cache.invalidate_report(user.org_id)` upon booking creation.

### Bug 18 — Booking Cancellation Fails to Invalidate Availability Cache
*   **File Location:** `app/routers/bookings.py`, lines 216–218
*   **What was the bug:** Cancelling a booking did not invalidate the availability cache.
*   **Why it caused incorrect behavior:** Cancelled slots remained marked as "busy" in availability responses.
*   **How it was fixed:** Added a call to `cache.invalidate_availability(...)` in the cancellation handler.

### Bug 19 — CSV Export Data Leak (Multi-Tenancy Violation)
*   **File Location:** `app/services/export.py`, lines 48–52
*   **What was the bug:** If a request specified `include_all=true` and a `room_id`, the system skipped the organization filter entirely.
*   **Why it caused incorrect behavior:** Administrators could download CSV records containing booking details belonging to rooms in other organizations.
*   **How it was fixed:** Ensured that all export query pathways are strictly scoped to the administrator's organization ID.

### Bug 20 — CSV Export Missing Room Tenancy Verification
*   **File Location:** `app/services/export.py`, line 38
*   **What was the bug:** When requesting a CSV export for a specific `room_id`, the system returned an empty list with `200 OK` if the room belonged to another organization.
*   **Why it caused incorrect behavior:** It violated the multi-tenancy rule that cross-org resource IDs must behave as non-existent and return `404 ROOM_NOT_FOUND`.
*   **How it was fixed:** Added a check verifying room ownership before querying export data: if the room is not found in the administrator's organization, raise `404 ROOM_NOT_FOUND`.

### Bug 21 — Malformed Datetime Input Causes HTTP 500
*   **File Location:** `app/timeutils.py`, line 11
*   **What was the bug:** The booking creation payload defined datetime inputs as strings. Parsing these strings via `datetime.fromisoformat()` threw a raw `ValueError` on malformed inputs.
*   **Why it caused incorrect behavior:** Uncaught `ValueError` exceptions caused the server to return an unhandled `500 Internal Server Error`.
*   **How it was fixed:** Added try-except handlers around parsing calls and converted failures to `400 INVALID_BOOKING_WINDOW`.

---

## 3. Concurrency & Race Condition Bugs

### Bug 22 — Double Booking Under Concurrency
*   **File Location:** `app/routers/bookings.py`, lines 100–117
*   **What was the bug:** Conflict checks were not synchronized with database insertion.
*   **Why it caused incorrect behavior:** Multiple concurrent requests for the same slot could verify that the slot was open before any transaction committed, leading to duplicate confirmed bookings.
*   **How it was fixed:** Introduced a thread synchronization lock (`_booking_lock`) around conflict verification and insertion steps.

### Bug 23 — Quota Limit Bypass Under Concurrency
*   **File Location:** `app/routers/bookings.py`, line 103
*   **What was the bug:** The check for the 3-booking rolling quota ran asynchronously.
*   **Why it caused incorrect behavior:** A member could submit multiple requests in parallel and bypass the quota limit before the database updated.
*   **How it was fixed:** Synchronized the quota auditing step within the `_booking_lock` block.

### Bug 24 — Rate Limiter Count Overwrite
*   **File Location:** `app/services/ratelimit.py`, lines 18–26
*   **What was the bug:** The rate limiter fetched, modified, and saved historical logs without synchronization.
*   **Why it caused incorrect behavior:** Concurrent requests from the same user resulted in race conditions that dropped records, allowing users to exceed the rate limit of 20 requests per 60 seconds.
*   **How it was fixed:** Added a lock protecting the read-modify-write process of user rate limits.

### Bug 25 — Reference Code Duplication
*   **File Location:** `app/services/reference.py`, lines 17–21
*   **What was the bug:** The increment of the reference counter contained an unsynchronized delay.
*   **Why it caused incorrect behavior:** Parallel requests read the same value, generating duplicate reference codes.
*   **How it was fixed:** Enforced synchronization around code generation using a thread lock.

### Bug 26 — Room Stats Count Overwrites
*   **File Location:** `app/services/stats.py`, lines 15–26
*   **What was the bug:** Statistics updates read the current state, paused, and wrote updates without safety locks.
*   **Why it caused incorrect behavior:** Concurrent updates caused writes to overwrite each other, leading to inaccurate stats.
*   **How it was fixed:** Wrapped increments and decrements inside a thread lock.

### Bug 27 — Concurrent Cancel Double Refund
*   **File Location:** `app/routers/bookings.py`, lines 195–214
*   **What was the bug:** The booking status check and database update were not performed atomically.
*   **Why it caused incorrect behavior:** Two concurrent cancellation requests could both verify that the booking status was confirmed, issuing two separate refunds.
*   **How it was fixed:** Used a database update statement to atomically claim the cancellation transition (`status = "confirmed"` $\rightarrow$ `"cancelled"`), raising `409 ALREADY_CANCELLED` if zero rows were affected.

### Bug 28 — Deadlock Hangs Server
*   **File Location:** `app/services/notifications.py`, lines 24–35
*   **What was the bug:** `notify_created` acquired `_email_lock` then `_audit_lock`, while `notify_cancelled` acquired `_audit_lock` then `_email_lock`.
*   **Why it caused incorrect behavior:** This inverse acquisition order caused an ABBA deadlock under concurrent bookings/cancellations, freezing the application.
*   **How it was fixed:** Realigned locking order in both methods to be identical (`_email_lock` outer, `_audit_lock` inner).

---

## 4. Robustness & Persistence Bugs

### Bug 29 — Stats Reset on Server Restart
*   **File Location:** `app/services/stats.py`, line 8
*   **What was the bug:** The dict containing room stats (`_stats`) was held solely in-memory.
*   **Why it caused incorrect behavior:** Restarting the server reset stats to zero, violating consistency.
*   **How it was fixed:** Added a startup routine `_init_startup_state()` in `app/main.py` that queries the SQLite database to aggregate counts and revenues for all confirmed bookings on boot.

### Bug 30 — Reference Counter Reset on Server Restart
*   **File Location:** `app/services/reference.py`, line 8
*   **What was the bug:** The monotonic sequence counter was held solely in-memory, resetting to `1000` on startup.
*   **Why it caused incorrect behavior:** Restarting the server caused the system to duplicate previously issued reference codes.
*   **How it was fixed:** Updated the startup routine in `app/main.py` to retrieve the maximum existing reference code suffix from the database and initialize the counter to that value + 1.

### Bug 31 — Cancellation and Refund Not Committed Atomically
*   **File Locations:** `app/services/refunds.py`, line 23 and `app/routers/bookings.py`, lines 211–218
*   **What was the bug:** `log_refund()` called `db.commit()` internally, committing the `RefundLog` as a standalone transaction. The booking status flip was committed separately in a prior `db.commit()` inside `cancel_booking`.
*   **Why it caused incorrect behavior:** If the server crashed between the two commits, the booking would be permanently marked `"cancelled"` with no corresponding `RefundLog` entry — violating the invariant that every cancelled booking has exactly one refund record.
*   **How it was fixed:** Removed `db.commit()` from `log_refund()` so it only stages the entry. In `cancel_booking`, a single `db.commit()` is called after both the status update and `log_refund()` are staged, making the two writes fully atomic.

### Bug 32 — `reference_code` Column Missing Database-Level Unique Constraint
*   **File Location:** `app/models.py`, line 55
*   **What was the bug:** The `reference_code` column was declared with `index=True` only, no `unique=True`.
*   **Why it caused incorrect behavior:** The in-memory counter lock enforces uniqueness at the application layer, but there is no database-level guard. Any edge case that bypasses the lock (e.g., a corrupted or mis-seeded counter after restart) would silently insert duplicate reference codes, directly violating Rule 7.
*   **How it was fixed:** Changed the column to `Column(String, nullable=False, unique=True, index=True)` so the database engine enforces uniqueness as a hard constraint.

### Bug 33 — CSV Export Uses `\r\n` Line Endings
*   **File Location:** `app/services/export.py`, line 49
*   **What was the bug:** `csv.writer(buffer)` uses `\r\n` as the default line terminator (Python's `csv` module RFC 4180 default).
*   **Why it caused incorrect behavior:** Any consumer that reads the CSV by splitting on `\n` will include a stray `\r` at the end of each row's last field, corrupting the `price_cents` value and breaking exact-match assertions.
*   **How it was fixed:** Passed `lineterminator="\n"` to `csv.writer` to produce Unix-style line endings.

---

## Summary Table

| # | Area | File | One-liner |
|---|------|------|-----------|
| 1 | Auth | `app/auth.py:52` | Access token exp−iat = 54000 s, not 900 s |
| 2 | Auth | `app/auth.py:109` | Logout stores jti but checks sub → revocation no-op |
| 3 | Auth | `app/routers/auth.py:45` | Refresh tokens reusable (not single-use) |
| 4 | Auth | `app/routers/auth.py:45` | Duplicate username → 201 + account leak, not 409 USERNAME_TAKEN |
| 5 | Validation | `app/timeutils.py:13` | TZ offset stripped instead of converted to UTC |
| 6 | Booking | `app/routers/bookings.py:55` | Inclusive overlap → back-to-back bookings rejected |
| 7 | Booking | `app/routers/bookings.py:94` | 5-min grace window for past start_time |
| 8 | Booking | `app/routers/bookings.py:101` | No min-duration / end>start check → 0 or negative price |
| 9 | Booking | `app/routers/bookings.py:166` | Detail start_time overwritten with created_at |
| 10 | Booking | `app/routers/bookings.py:174` | Members can read other members' bookings |
| 11 | Booking | `app/routers/bookings.py:147` | List sorted descending, not ascending |
| 12 | Booking | `app/routers/bookings.py:148` | offset(page·limit) skips first page |
| 13 | Booking | `app/routers/bookings.py:149` | limit hardcoded to 10 |
| 14 | Refund | `app/routers/bookings.py:222` | ≥48 h notice gets 50% instead of 100% |
| 15 | Refund | `app/routers/bookings.py:227` | <24 h notice gets 50% instead of 0% |
| 16 | Refund | `app/routers/bookings.py:231` + `app/services/refunds.py:15` | Wrong rounding; response ≠ RefundLog |
| 17 | Cache | `app/routers/bookings.py:131` | Create doesn't invalidate usage-report cache |
| 18 | Cache | `app/routers/bookings.py:239` | Cancel doesn't invalidate availability cache |
| 19 | Tenancy | `app/services/export.py:46` | include_all+room_id exports another org's data |
| 20 | Tenancy | `app/services/export.py:41` | Cross-org room_id returns 200 instead of 404 |
| 21 | Robustness | `app/timeutils.py:11` | Malformed datetime → uncaught 500 instead of 400 |
| 22 | Concurrency | `app/routers/bookings.py:109` | Double-booking race (check-then-insert) |
| 23 | Concurrency | `app/routers/bookings.py:113` | Quota bypass race |
| 24 | Concurrency | `app/services/ratelimit.py:23` | Rate limiter lost updates → never 429s |
| 25 | Concurrency | `app/services/reference.py:22` | Duplicate reference codes under concurrency |
| 26 | Concurrency | `app/services/stats.py:19` | Stats lost updates under concurrency |
| 27 | Concurrency | `app/routers/bookings.py:211` | Concurrent cancel → double refund |
| 28 | Concurrency | `app/services/notifications.py:24` | ABBA lock-order deadlock hangs service |
| 29 | Persistence | `app/services/stats.py:9` | Stats cache resets to 0 on server restart |
| 30 | Persistence | `app/services/reference.py:9` | Reference code counter resets on server restart |
| 31 | Atomicity | `app/services/refunds.py:23` + `app/routers/bookings.py:216` | Status flip and RefundLog committed in two separate transactions |
| 32 | Data Integrity | `app/models.py:55` | `reference_code` missing DB-level `unique=True` constraint |
| 33 | Export | `app/services/export.py:49` | CSV export uses `\r\n` line endings instead of `\n` |

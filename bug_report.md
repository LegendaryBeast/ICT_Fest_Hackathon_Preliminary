# Bug Report — CoWork API

This report documents the 46 bugs identified and resolved in the CoWork API codebase. Each entry details the file location, the nature of the issue, why it caused incorrect behavior, and how it was fixed to satisfy the API contract.

---

## 1. Authentication & Session Control Bugs

### Bug 1 — Access Token Expiry Calculated Incorrectly
*   **File Location:** `app/auth.py`, line 52
*   **What was the bug:** The code defined access token lifetime as `lifetime = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES * 60)`. This multiplied 15 minutes by 60, resulting in 900 minutes (15 hours) instead of 900 seconds (15 minutes).
*   **Why it caused incorrect behavior:** It violated the specification requiring access tokens to expire in exactly 900 seconds.
*   **How it was fixed:** Changed the calculation to `lifetime = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)`.

### Bug 2 — Logout Revoked Check Uses Wrong Claim
*   **File Location:** `app/auth.py`, line 109
*   **What was the bug:** The logout endpoint added the token's `jti` to `_revoked_tokens`, but `get_token_payload` checked if the user identifier `sub` was in `_revoked_tokens`.
*   **Why it caused incorrect behavior:** Because a token's `sub` (the user ID) never matched the UUID hex in `_revoked_tokens`, logged-out tokens remained active and valid.
*   **How it was fixed:** Corrected the lookup to check for the token identifier `jti`: `if payload.get("jti") in _revoked_tokens: raise AppError(...)`.

### Bug 3 — Registration Does Not Return 409 for Duplicate Username
*   **File Location:** `app/routers/auth.py`, lines 40–46
*   **What was the bug:** Registering an existing username inside the same organization returned a `201 Created` response containing the original user's details.
*   **Why it caused incorrect behavior:** It violated the rule that duplicate registration within an organization must return `409 USERNAME_TAKEN`.
*   **How it was fixed:** Replaced the early-return logic with raising `AppError(409, "USERNAME_TAKEN", ...)`.

### Bug 4 — Refresh Tokens Are Not Single-Use
*   **File Location:** `app/routers/auth.py`, line 93
*   **What was the bug:** The refresh endpoint processed tokens without checking or recording whether they had been previously consumed.
*   **Why it caused incorrect behavior:** It violated the requirement that refresh tokens are single-use only.
*   **How it was fixed:** Implemented a thread-safe helper `consume_token_jti()` that checks and records used refresh JTIs in the revocation set, returning a `401` error on reuse.

### Bug 5 — Datetime Timezone Conversion Strips Offset
*   **File Location:** `app/timeutils.py`, line 13
*   **What was the bug:** When parsing datetimes, the code stripped the timezone offset using `dt.replace(tzinfo=None)` without converting it to UTC first.
*   **Why it caused incorrect behavior:** It kept the local wall time instead of the absolute instant (e.g., `18:00+06:00` became `18:00 UTC` instead of `12:00 UTC`), resulting in corrupted pricing and reservation slots.
*   **How it was fixed:** Normalization to UTC was added: `dt = dt.astimezone(timezone.utc).replace(tzinfo=None)`.

---

## 2. Input Validation & Booking Logic Bugs

### Bug 6 — Start Time Allows 5-Minute Grace Window in the Past
*   **File Location:** `app/routers/bookings.py`, line 94
*   **What was the bug:** The start-time check `if start <= now - timedelta(seconds=300)` permitted users to create bookings starting up to 5 minutes in the past.
*   **Why it caused incorrect behavior:** It violated the rule that the booking start time must be strictly in the future.
*   **How it was fixed:** Changed the conditional statement to `if start <= now:`.

### Bug 7 — Overlap Check Blocks Back-to-Back Bookings
*   **File Location:** `app/routers/bookings.py`, line 55
*   **What was the bug:** The reservation conflict check used `<=` instead of `<` in `b.start_time <= end and start <= b.end_time`.
*   **Why it caused incorrect behavior:** Adjacent bookings (e.g., one ending at 10:00 and another starting at 10:00) were incorrectly flagged as overlapping.
*   **How it was fixed:** Updated the conflict logic to check for strict overlap: `b.start_time < end and start < b.end_time`.

### Bug 8 — Missing Minimum Duration Check
*   **File Location:** `app/routers/bookings.py`, line 101
*   **What was the bug:** The API validated maximum duration but did not check minimum duration limits.
*   **Why it caused incorrect behavior:** Bookings shorter than `MIN_DURATION_HOURS` could be created.
*   **How it was fixed:** Enforced duration bounds: `if duration_hours < MIN_DURATION_HOURS or duration_hours > MAX_DURATION_HOURS: raise AppError(...)`.

### Bug 9 — Missing `end_time > start_time` Validation
*   **File Location:** `app/routers/bookings.py`, line 97
*   **What was the bug:** Failed to validate that `end_time` is logically after `start_time`.
*   **Why it caused incorrect behavior:** Negative or zero-duration bookings could be stored.
*   **How it was fixed:** Enforced duration checks that implicitly prevent zero/negative hours.

### Bug 10 — `list_bookings` Ordering, Offset, and Limit
*   **File Location:** `app/routers/bookings.py`, lines 147–149
*   **What was the bug:** Bookings returned by `GET /bookings` were sorted descending, used `page * limit` as offset (skipping page 1), and hardcoded the limit to 10.
*   **Why it caused incorrect behavior:** It violated chronological sorting and broke standard pagination behavior.
*   **How it was fixed:** Changed to `Booking.start_time.asc()`, `(page - 1) * limit`, and `.limit(limit)`.

### Bug 11 — `get_booking` Overwrites `start_time`
*   **File Location:** `app/routers/bookings.py`, line 177
*   **What was the bug:** The endpoint accidentally reassigned `booking.start_time = booking.created_at` before serialization.
*   **Why it caused incorrect behavior:** The response payload incorrectly showed the reservation creation time as the start time.
*   **How it was fixed:** Removed the line overriding `response["start_time"]`.

### Bug 12 — Refund Policy < 24h Returns 50%
*   **File Location:** `app/routers/bookings.py`, line 227
*   **What was the bug:** The final fallback branch of the cancellation notice check set `refund_percent = 50`.
*   **Why it caused incorrect behavior:** Late cancellations (notice $< 24$ hours) received a 50% refund instead of 0%.
*   **How it was fixed:** Updated the fallback to set `refund_percent = 0`.

### Bug 13 — `refund_amount_cents` Inconsistency
*   **File Location:** `app/routers/bookings.py`, line 231
*   **What was the bug:** Cancel response computed `refund_amount_cents` independently from `log_refund()`.
*   **Why it caused incorrect behavior:** Different rounding could cause database and API responses to diverge.
*   **How it was fixed:** Unified calculations to integer math using half-up rounding.

### Bug 14 — Refund Rounding Uses Truncation Instead of Half-Up
*   **File Location:** `app/services/refunds.py`, line 17
*   **What was the bug:** The refund amount was computed using float representation, resulting in integer truncation.
*   **Why it caused incorrect behavior:** Half-cents did not round up correctly.
*   **How it was fixed:** Changed calculation to integer math using half-up rounding.

### Bug 15 — Reference Code Counter Is Not Atomic
*   **File Location:** `app/services/reference.py`, line 19
*   **What was the bug:** Monotonic sequence generation lacked thread synchronization.
*   **Why it caused incorrect behavior:** Parallel requests read the same value, generating duplicate reference codes.
*   **How it was fixed:** Protected with `threading.Lock()`.

---

## 3. Concurrency & Performance Bugs

### Bug 16 — Rate Limiter Records Request Before Checking Limit
*   **File Location:** `app/services/ratelimit.py`, line 26
*   **What was the bug:** Request appended to the rolling window bucket before the limit check.
*   **Why it caused incorrect behavior:** Blocked/rate-limited requests consumed quota spaces, locking out legitimate requests.
*   **How it was fixed:** Check `len(bucket) >= _MAX_REQUESTS` before appending.

### Bug 17 — Room Stats Use Inconsistent In-Memory Cache
*   **File Location:** `app/services/stats.py`, line 9
*   **What was the bug:** Confirmed booking counts and revenue were tracked incrementally using a local dictionary.
*   **Why it caused incorrect behavior:** Stale stats resulted under concurrency, and rebooting the server reset stats to 0.
*   **How it was fixed:** Query the DB directly with `COUNT/SUM` aggregates for stats requests.

### Additional Fix — Cache Invalidation Gaps
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** Booking actions failed to invalidate usage report and availability caches.
*   **Why it caused incorrect behavior:** Outdated report and busy slots were served.
*   **How it was fixed:** Added explicit invalidation triggers to booking create/cancel.

### Bug 18 — Deadlock in Notifications Service
*   **File Location:** `app/services/notifications.py`, lines 24–35
*   **What was the bug:** `notify_created` acquired `_email_lock` then `_audit_lock`, while `notify_cancelled` acquired `_audit_lock` then `_email_lock`.
*   **Why it caused incorrect behavior:** Lock-order inversion caused deadlocks under concurrent traffic.
*   **How it was fixed:** Aligned locking order in both methods to be identical (`_email_lock` outer, `_audit_lock` inner).

### Bug 19 — Double Cancel Race Condition
*   **File Location:** `app/routers/bookings.py`, line 211
*   **What was the bug:** Status check and refund write were separate steps.
*   **Why it caused incorrect behavior:** Two concurrent requests could cancel the same booking and double-refund.
*   **How it was fixed:** Implemented atomic SQL updates to change status and check affected rows.

### Bug 20 — Multi-Tenancy Bypass in Export
*   **File Location:** `app/services/export.py`
*   **What was the bug:** Exporting by `room_id` with `include_all=True` skipped the organization ownership check.
*   **Why it caused incorrect behavior:** Allowed admins to download CSV records belonging to other organizations' rooms.
*   **How it was fixed:** Scoped all export queries to the administrator's org ID.

### Bug 21 — `get_booking` Allows Cross-Member Read
*   **File Location:** `app/routers/bookings.py`, line 174
*   **What was the bug:** Only room org membership was verified, not user ownership.
*   **Why it caused incorrect behavior:** Allowed members to fetch booking details belonging to other users.
*   **How it was fixed:** Added role validation checks.

### Bug 22 & Bug 23 — Concurrency Races in Booking Creation
*   **File Location:** `app/routers/bookings.py`, line 109
*   **What was the bug:** Conflict check and database write were not atomic.
*   **Why it caused incorrect behavior:** Concurrent requests for the same room/time both verified the slot was open, producing overlapping bookings.
*   **How it was fixed:** Wrapped the check-and-insert block in a global thread lock (`_booking_lock`).

### Bug 24 — Missing Duplicate Name Check on Room Creation
*   **File Location:** `app/routers/rooms.py`
*   **What was the bug:** The create_room endpoint did not verify room name availability before insertion.
*   **Why it caused incorrect behavior:** Caused database integrity violations, returning raw 500 errors.
*   **How it was fixed:** Query the database and return `409 ROOM_NAME_TAKEN` explicitly.

### Bug 25 — Missing Validation on Room Capacity and Rate
*   **File Location:** `app/routers/rooms.py`
*   **What was the bug:** Accepted negative values for capacity and hourly rate.
*   **Why it caused incorrect behavior:** Led to invalid room entries and negative reservation pricing.
*   **How it was fixed:** Explicitly reject values where capacity $\le 0$ or rate $< 0$.

### Bug 26 — Missing Database UniqueConstraint on Room
*   **File Location:** `app/models.py`
*   **What was the bug:** The Room model did not declare unique constraints on `org_id` and `name`.
*   **Why it caused incorrect behavior:** Allowed duplicate names to be stored in the database if application-level checks failed.
*   **How it was fixed:** Added `UniqueConstraint("org_id", "name")` to the Room model schema.

### Bug 27 — Missing Unique Constraint on Reference Code
*   **File Location:** `app/models.py`
*   **What was the bug:** Reference codes lacked a DB-level unique constraint.
*   **Why it caused incorrect behavior:** Duplicate references could be stored if application checks failed.
*   **How it was fixed:** Added `unique=True` to the `reference_code` column on the Booking model.

### Bug 28 — Room Creation Fails to Invalidate Report Cache
*   **File Location:** `app/routers/rooms.py`
*   **What was the bug:** Creating a new room did not invalidate the usage report cache.
*   **Why it caused incorrect behavior:** The new room was omitted from report results until the cache expired.
*   **How it was fixed:** Added cache invalidation calls upon room creation.

### Bug 29 — Missing Past Booking Check on Cancellation
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** Notice time was calculated but negative values (past bookings) were not caught.
*   **Why it caused incorrect behavior:** Allowed users to cancel bookings that had already started.
*   **How it was fixed:** Added an explicit validation check preventing past booking cancellation.

### Bug 30 — Admin List Bookings Missing Org Scope
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** List booking queries unconditionally filtered by `user_id`.
*   **Why it caused incorrect behavior:** Administrative users could not see bookings other members had made.
*   **How it was fixed:** If user role is `admin`, load all bookings matching the organization ID.

### Bug 31 — Artificial Sleeps Still Active Inside Global Booking Lock
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** Internal warmup and audit delays ran inside the critical synchronized lock.
*   **Why it caused incorrect behavior:** Serialized all booking attempts, causing major request queues and timeouts.
*   **How it was fixed:** Removed `_pricing_warmup`, `_quota_audit`, and `_settlement_pause` sleeps.

### Bug 32 — Start Time Check Uses `>=` Instead of `>`
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** Guard checked `start >= now`.
*   **Why it caused incorrect behavior:** Permitted bookings starting exactly at the current instant, which immediately became past bookings.
*   **How it was fixed:** Changed condition to `start <= now` (requiring strict future starts).

### Bug 33 — Revoked Token Set Grows Without Bound
*   **File Location:** `app/auth.py`
*   **What was the bug:** Revoked tokens were added to an in-memory set that grew infinitely.
*   **Why it caused incorrect behavior:** Led to memory exhaustion (OOM) over time.
*   **How it was fixed:** Changed to `dict[jti, exp]` and implemented an automated pruning routine (`_prune_revoked()`).

### Bug 34 — Cache Module Has No Thread Safety
*   **File Location:** `app/cache.py`
*   **What was the bug:** cache operations mutated python dictionaries concurrently without lock protection.
*   **Why it caused incorrect behavior:** Raced updates caused dictionary corruption and stale cache records.
*   **How it was fixed:** Wrapped all cache reads/writes with a thread-safe `Lock()`.

### Bug 35 — Usage Report Accepts Inverted Date Range Silently
*   **File Location:** `app/routers/admin.py`
*   **What was the bug:** Setting `from > to` returned an empty report.
*   **Why it caused incorrect behavior:** Provided a structural but empty report instead of signaling error.
*   **How it was fixed:** Added validations to verify `from_date <= to_date`.

### Bug 36 — Database Session Missing Rollback on Exception
*   **File Location:** `app/database.py`
*   **What was the bug:** Handlers closing connection on errors failed to roll back in-flight transactions.
*   **Why it caused incorrect behavior:** Kept database connections in corrupted states within the pool.
*   **How it was fixed:** Added explicit `db.rollback()` within transaction exceptions.

### Bug 37 — Z Suffix Not Supported in Python 3.9 `fromisoformat()`
*   **File Location:** `app/timeutils.py`
*   **What was the bug:** Trailing "Z" (UTC indicator) raised ValueErrors.
*   **Why it caused incorrect behavior:** ISO 8601 strings crashed standard parsing.
*   **How it was fixed:** Normalized `"Z"` to `"+00:00"` prior to parsing.

### Bug 38 — Booking Quota Incorrectly Applied to Admins
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** Admin reservations were blocked by the rolling 3-booking quota limit.
*   **Why it caused incorrect behavior:** Prevented administrative overrides.
*   **How it was fixed:** Quota limit check is skipped for admins.

### Bug 39 — `_pricing_warmup()` sleep inside SQLite write lock
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** Warmup sleep executed within the SQLite exclusive transaction write lock.
*   **Why it caused incorrect behavior:** Blocked all concurrent SQLite database writes.
*   **How it was fixed:** Removed the warmup sleep entirely.

### Bug 40 — `_quota_audit()` sleep inside SQLite write lock
*   **File Location:** `app/routers/bookings.py`
*   **What was the bug:** Quota checks slept inside the exclusive lock.
*   **Why it caused incorrect behavior:** Blocked database operations.
*   **How it was fixed:** Removed the audit sleep entirely.

### Bug 41 — `_aggregate_pause()` sleep inside `_stats_lock`
*   **File Location:** `app/services/stats.py`
*   **What was the bug:** increment/decrement slept 100ms inside the stats lock.
*   **Why it caused incorrect behavior:** Serialized all statistics gathering and calculations.
*   **How it was fixed:** Removed the aggregate pause sleep.

### Bug 42 — `_settle_pause()` sleep inside `_ratelimit_lock`
*   **File Location:** `app/services/ratelimit.py`
*   **What was the bug:** Settle pause held the global ratelimit lock.
*   **Why it caused incorrect behavior:** Prevented multiple users from requesting actions concurrently.
*   **How it was fixed:** Removed the settle pause sleep.

### Bug 43 — `_format_pause()` sleep inside `_reference_lock`
*   **File Location:** `app/services/reference.py`
*   **What was the bug:** Formatting step delayed reference sequence updates.
*   **Why it caused incorrect behavior:** Serialized reference numbering.
*   **How it was fixed:** Removed the format pause sleep.

### Bug 44 — Notification sleeps serializing all requests
*   **File Location:** `app/services/notifications.py`
*   **What was the bug:** SMTP and log delays executed inside the notification locks.
*   **Why it caused incorrect behavior:** Blocked other unrelated requests during notification dispatch.
*   **How it was fixed:** Removed the simulated SMTP and logging delays.

### Bug 45 — Org registration TOCTOU race causes 500 error
*   **File Location:** `app/routers/auth.py`
*   **What was the bug:** Concurrent requests registering the same org both attempted insertion.
*   **Why it caused incorrect behavior:** The second request crashed with an unhandled unique constraint error.
*   **How it was fixed:** Wrapped organization registration in exception rollback handling to join existing orgs.

### Bug 46 — stats.record_cancel allows negative revenue
*   **File Location:** `app/services/stats.py`
*   **What was the bug:** Incremental cancellations subtracted directly from the in-memory stats.
*   **Why it caused incorrect behavior:** Stats revenue totals could drop below zero.
*   **How it was fixed:** Aggregated stats directly via database queries.

---

## Summary Table

| ID | functional Area | File Location | Nature of Defect |
|:---|:---|:---|:---|
| 1 | Auth | `app/auth.py` | Access token exp is 15 hours, not 15 minutes |
| 2 | Auth | `app/auth.py` | Logout blacklists `jti` but token payload checks `sub` |
| 3 | Auth | `app/routers/auth.py` | Duplicate username registration returns 201 instead of 409 |
| 4 | Auth | `app/routers/auth.py` | Refresh tokens can be reused indefinitely |
| 5 | Validation | `app/timeutils.py` | timezone offset is stripped instead of converted to UTC |
| 6 | Booking | `app/routers/bookings.py` | Bookings in the past allowed via a 5-minute grace window |
| 7 | Booking | `app/routers/bookings.py` | Adjacent bookings rejected due to non-strict overlap check |
| 8 | Booking | `app/routers/bookings.py` | Missing validation for `MIN_DURATION_HOURS` |
| 9 | Booking | `app/routers/bookings.py` | Missing validation for positive duration (`end_time > start_time`) |
| 10 | Booking | `app/routers/bookings.py` | list_bookings sorted descending, skips page 1, hardcodes limit |
| 11 | Booking | `app/routers/bookings.py` | start_time in reservation details overwritten by created_at |
| 12 | Refund | `app/routers/bookings.py` | Cancellations made with <24h notice return 50% instead of 0% |
| 13 | Refund | `app/routers/bookings.py` | response `refund_amount_cents` diverges from logged database value |
| 14 | Refund | `app/services/refunds.py` | Float calculation uses truncation instead of half-up rounding |
| 15 | Concurrency | `app/services/reference.py` | Code sequence counter is non-atomic and causes duplicates |
| 16 | Concurrency | `app/services/ratelimit.py` | Token limits appended before verification, locking out space |
| 17 | Concurrency | `app/services/stats.py` | In-memory stats are non-atomic and reset to 0 on reboot |
| 18 | Concurrency | `app/services/notifications.py` | AB-BA lock inversion creates deadlocks on create vs cancel |
| 19 | Concurrency | `app/routers/bookings.py` | Concurrently canceled bookings issue double refunds |
| 20 | Tenancy | `app/services/export.py` | include_all + room_id parameter bypasses organization boundary |
| 21 | Tenancy | `app/routers/bookings.py` | Members can retrieve details for other users' bookings |
| 22 | Concurrency | `app/routers/bookings.py` | Concurrency check-then-insert race allows double bookings |
| 23 | Concurrency | `app/routers/bookings.py` | Concurrency quota check allows quota bypass |
| 24 | Validation | `app/routers/rooms.py` | Duplicate room names inside org yield raw 500 error |
| 25 | Validation | `app/routers/rooms.py` | Negative values allowed for capacity and hourly rate |
| 26 | Data Integrity | `app/models.py` | Missing UniqueConstraint for (org_id, name) on Room table |
| 27 | Data Integrity | `app/models.py` | Missing UniqueConstraint on reference_code |
| 28 | Cache | `app/routers/rooms.py` | Room creation does not invalidate usage report cache |
| 29 | Validation | `app/routers/bookings.py` | Past reservations can be cancelled |
| 30 | Tenancy | `app/routers/bookings.py` | Admins cannot list other members' bookings |
| 31 | Performance | `app/routers/bookings.py` | Warmup, audit, and pause sleeps hold critical booking lock |
| 32 | Validation | `app/routers/bookings.py` | Start time check uses `>=` instead of strict future `>` |
| 33 | Robustness | `app/auth.py` | Revoked token set grows infinitely without memory boundaries |
| 34 | Concurrency | `app/cache.py` | In-memory caches modified concurrently without mutex locks |
| 35 | Validation | `app/routers/admin.py` | Usage report silently processes inverted date windows |
| 36 | Robustness | `app/database.py` | Uncaught exceptions inside router sessions bypass connection rollback |
| 37 | Robustness | `app/timeutils.py` | ISO datetimes with Z suffix raise ValueError on python 3.9 |
| 38 | Validation | `app/routers/bookings.py` | Member booking quotas incorrectly applied to administrator users |
| 39 | Concurrency | `app/routers/bookings.py` | _pricing_warmup warmup sleeps under SQLite exclusive write lock |
| 40 | Concurrency | `app/routers/bookings.py` | _quota_audit audit sleeps under SQLite exclusive write lock |
| 41 | Concurrency | `app/services/stats.py` | incremental aggregation sleeps hold stats lock |
| 42 | Concurrency | `app/services/ratelimit.py` | bookkeeping sleeps lock out rate limit checks |
| 43 | Concurrency | `app/services/reference.py` | prefix padding format sleeps lock reference sequences |
| 44 | Concurrency | `app/services/notifications.py` | SMTP and file formatting sleeps serialize post-commit pipelines |
| 45 | Concurrency | `app/routers/auth.py` | Org registration TOCTOU causes duplicate insert 500 error |
| 46 | Concurrency | `app/services/stats.py` | incremental statistics decrement drops below 0 |

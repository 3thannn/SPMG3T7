# Test Cases for US14.4: Holds Expire Automatically

> As the system, I want tentative holds to expire automatically at their deadline,
> so that venues don't stay blocked by holds nobody followed up on.

## Acceptance Criteria

| # | Criterion | Status |
| --- | --- | --- |
| AC1 | A scheduled job checks holds at least every 15 minutes (team-chosen) | Done — pg_cron, every 15 minutes. Scheduled on the live project 2026-10-26; see "Recorded results" |
| AC2 | Holds past their expiry → Expired, and the slot is freed for other requests | Done |
| AC3 | Coordinator is notified 24h before expiry (assumption, customer to confirm) and again when it expires (US10.2) | Done |
| AC4 | Expired holds stay in history and can't be turned into a booking request | Done |
| AC5 | First time using a scheduler (e.g. Supabase pg_cron), so sized up for uncertainty | pg_cron chosen; setup and checks below |

## Rolling it out (read this before running anything)

Two SQL scripts, run at different times, because the database is shared:

1. **`SUPABASE_US14_4_HOLD_EXPIRY.sql` — any time.** Adds the `Expired` booking
   status, the `expiry_warned_at` column and the `sweep_tentative_holds()` function.
   Nothing calls the function yet, so nothing changes.
2. **`SUPABASE_US14_4_SCHEDULE_HOLD_SWEEP.sql` — only after this story is merged
   and everyone has pulled.** Turns on pg_cron and schedules the sweep. From its
   first run the database holds `Expired` bookings, and code from before US14.4
   cannot read that status: every bookings, holds and venue page on an older
   checkout would answer 500.

**Status:** both are applied to the live project, step 1 on 2026-10-21 and step 2
on 2026-10-26.

Until step 2 runs, holds still free their slot at the deadline (US14.3's rule);
only the `Expired` status and the two notices wait for it.

## Team assumptions (not customer-confirmed)

- **"Expire automatically at their deadline."** The slot is free the moment the
  deadline passes, because every availability check compares the expiry with the
  clock (US14.3), not only when the job next runs. The job, at most 15 minutes
  later, records it (Held → Expired) and tells the Coordinator. A hold past its
  deadline that the job has not reached yet is treated exactly like an Expired one.
- **Expiry itself counts** (an expiry of 17:00 has expired at 17:00), as in US14.3.
  Times are Singapore local time, like the booking times.
- **The 24-hour warning** goes out once per hold. A hold placed with less than a day
  to go is warned about at the first sweep after it is placed. A hold that expires
  between two sweeps before it was warned gets only the "expired" notice.
- **Nobody is notified** about a hold on an event with no Coordinator, or on a
  Completed, Cancelled or Rejected event. The hold still expires.
- **An expired hold cannot be cancelled** either: it is history, and its slot is
  already free. (US14.3 used to let the Coordinator "cancel" a lapsed hold.)
- **pg_cron rather than a backend scheduler**: it runs inside the database, so holds
  expire whether or not anyone's backend is running, and there is one job however
  many team members run the API locally.
- **The notices are written by the database**, in exactly the words US10.2 gave
  `notify_hold_expiring` and `notify_hold_expired`. `test_hold_expiry_db.py` checks
  they still agree.

## Workflow Visualization

```
Venue Staff place a hold ──► Held (expires at T)
                               │
        T − 24h ── sweep ──► "hold-expiring" notice to the Coordinator (once)
                               │
        Coordinator requests before T ──► Requested (left alone by the sweep)
                               │
        T ─────────────────► slot already free (every check reads the clock)
                               │
        next sweep (≤ 15 min) ─► Expired + "hold-expired" notice
                                 kept in history; request → 409 hold-expired;
                                 cancel → 409 hold-expired
```

## Test Files

| Layer | File |
| --- | --- |
| Backend (CI) | `backend/tests/test_hold_expiry_us14_4.py` |
| Backend (real database, opt-in) | `backend/tests/test_hold_expiry_db.py` — the sweep itself |
| Frontend | `EventBookings.test.tsx` (US14.4 test), `VenueHolds.test.tsx` (US14.4 test) |
| Database | `SUPABASE_US14_4_HOLD_EXPIRY.sql`, `SUPABASE_US14_4_SCHEDULE_HOLD_SWEEP.sql` |
| Database (SQL Editor, no DB URL needed) | `backend/TEST_US14_4_HOLD_EXPIRY.sql` — the same checks as the DB test, in one block that always rolls back; read the result from the error message |

Run the database test from `backend/` after step 1. It works in a transaction that
is always rolled back, so it leaves nothing in the shared project:

```bash
SPMG3T7_DB_TESTS=1 python -m pytest tests/test_hold_expiry_db.py          # bash
$env:SPMG3T7_DB_TESTS=1; python -m pytest tests/test_hold_expiry_db.py    # PowerShell
```

---

## 1. HAPPY PATH TEST CASES

### TC-E01: The sweep is scheduled at least every 15 minutes (AC1)
- **Expected Result**: `cron.schedule('sweep-tentative-holds', '*/15 * * * *', 'SELECT public.sweep_tentative_holds()')`
- **Automated**: `TestTheSchedule`

### TC-E02: A hold past its expiry becomes Expired (AC2)
- **Pre-conditions**: Held hold that expired a minute ago, on a Planning event assigned to a Coordinator
- **Test Steps**: `SELECT public.sweep_tentative_holds();`
- **Expected Result**: status Expired; its id in `"expired"`; the expiry is kept
- **Automated**: `test_the_sweep_expires_warns_and_tells_the_coordinator_once`, `test_an_expired_hold_keeps_its_expiry`

### TC-E03: The slot is free for other requests (AC2)
- **Expected Result**: `venue_slot_clashes` is false for the expired hold's slot and true for a live hold's; a Coordinator's request for the slot is 201
- **Automated**: `test_an_expired_hold_frees_its_slot_and_cannot_be_requested`, `TestTheSlotIsFree`

### TC-E04: The Coordinator is warned 24 hours before (AC3)
- **Pre-conditions**: Held hold expiring in 2 hours, not warned yet
- **Expected Result**: one `hold-expiring` notice to the Coordinator: `The tentative hold on <venue> for "<event>" expires 02 Nov 2027, 09:00.`; `expiry_warned_at` set
- **Automated**: `test_the_sweep_expires_warns_and_tells_the_coordinator_once`

### TC-E05: The Coordinator is told when it expires (AC3)
- **Expected Result**: one `hold-expired` notice: `The tentative hold on <venue> for "<event>" has expired.`
- **Automated**: same test; wording compared with `notify_hold_expired`

### TC-E06: An expired hold stays in history (AC4)
- **Expected Result**: the event's bookings list shows it as `Expired` with `holdExpired: true` and its expiry; the venue's holds list keeps it, marked expired; the page shows "Hold expired …" with no buttons
- **Automated**: `TestExpiredHoldsStayInHistory`; frontend "shows a hold the sweep marked Expired as expired", "lists a hold the sweep marked Expired as expired"

### TC-E07: An expired hold cannot be turned into a request (AC4)
- **Expected Result**: 409 `hold-expired`, "The hold on Great Hall expired at 2027-10-08 17:00. Ask Venue Staff to hold it again, or request the venue as a new booking."; in SQL, `request_held_booking` answers `not-held`
- **Automated**: `TestAnExpiredHoldCannotBeRequested`, `test_an_expired_hold_frees_its_slot_and_cannot_be_requested`

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-E10: Nothing happens twice
- **Expected Result**: a second sweep expires and warns nothing new and writes no notice
- **Automated**: `test_the_sweep_expires_warns_and_tells_the_coordinator_once`

### TC-E11: A sweep racing a Coordinator is reported as expired
- **Expected Result**: if the hold is swept between the route's check and its write, request and cancel both answer 409 `hold-expired`
- **Automated**: `test_a_sweep_between_the_check_and_the_write_is_reported_as_expired` (both classes)

### TC-E12: The rest of the system reads Expired as history
- **Expected Result**: never holds its venue (`HOLDS_VENUE`), never flagged for a conflict (US15.2), does not block the safety check (US4.4); a Held hold past its expiry reads the same before the sweep
- **Automated**: `TestTheExpiredStatus`, `TestTheSlotIsFree`

---

## 3. NEGATIVE TEST CASES

| ID | Scenario | Expected | Automated |
| --- | --- | --- | --- |
| TC-E20 | Hold expiring in 3 days | Not warned, not expired | DB test (`later`) |
| TC-E21 | Already warned, expiring in 1 hour | No second warning | DB test (`warned`) |
| TC-E22 | Hold on a Cancelled event, expired / due | Expires; no notice; not warned | DB test (`closed_*`) |
| TC-E23 | Requested booking that started as a hold, expiry passed | Left alone | DB test (`requested`) |
| TC-E24 | Cancel an Expired hold, or a Held one past expiry | 409 `hold-expired` "There is nothing to cancel."; unchanged | `test_there_is_nothing_to_cancel` |
| TC-E25 | An Expired hold's expiry removed | Refused by `venue_bookings_hold_has_expiry` | `test_an_expired_hold_keeps_its_expiry` |

## 4. BOUNDARY TEST CASES

| ID | Boundary | Expected | Automated |
| --- | --- | --- | --- |
| TC-E30 | Expiry exactly now | Expired (US14.3: expiry itself counts) | `hold_expired_at` (US14.3 tests TC-H22) |
| TC-E31 | A minute before expiry | Still Held, still requestable | US14.3 TC-H23, TC-H31 |
| TC-E32 | Schedule step | Divides the hour, at most 15 | `test_the_job_runs_at_least_every_15_minutes` |

## 5. Checks after scheduling (run manually in the Supabase SQL editor)

1. `SELECT jobname, schedule, active FROM cron.job;` → `sweep-tentative-holds`, `*/15 * * * *`, `true`.
2. After 15 minutes: `SELECT start_time, status, return_message FROM cron.job_run_details ORDER BY start_time DESC LIMIT 5;` → `succeeded`. `return_message` is only pg_cron's short status for the statement, not the sweep's `{"expired": [...], "warned": [...]}`; check 3 shows what a run did.
3. Place a hold expiring in ~20 minutes; within one sweep the Coordinator has a "Hold expiring" notice; after the expiry and one more sweep, a "Hold expired" notice and the hold shows Expired.

Recorded results:

| Check | Date | Result |
| --- | --- | --- |
| Backend `ruff check`, `compileall`, `pytest` | 2026-10-21 | 1619 passed, 1 skipped (the opt-in DB test) |
| Frontend `oxlint`, `build`, `vitest` | 2026-10-21 | Clean; all US14.4 tests pass. Unrelated: `UnassignedQueuePage` date-format test fails on a non-US locale, and some 5-second timeouts under full-suite load pass when run alone |
| Step 1 (`SUPABASE_US14_4_HOLD_EXPIRY.sql`) applied to the live project | 2026-10-21 | Applied |
| `TEST_US14_4_HOLD_EXPIRY.sql` against the live Supabase project | 2026-10-21 | **US14.4 PASSED - all 19 checks**; rolled back |
| `test_hold_expiry_db.py` (pytest, opt-in) | — | Not run: `SUPABASE_DB_URL` is not configured locally. It covers the same ground as the SQL Editor check |
| Step 2 (`SUPABASE_US14_4_SCHEDULE_HOLD_SWEEP.sql`) applied to the live project | 2026-10-26 | Applied, after US14.4 was merged (PR #34) and every pushed branch in progress included it |
| Backend `pytest` on `main` after US12.2 (PR #42): `test_hold_expiry_us14_4.py`, `test_venue_holds.py`, `test_cancel_event_us4_6.py`, `test_venue_unavailability.py` | 2026-10-26 | 345 passed |
| Checks 1 and 2 (`cron.job`, `cron.job_run_details`) | — | Not recorded yet. The job's runs also show in check 3: both notices were written within 0.11 s of :00 and :15 |
| Check 3, through the API against the live project, with no sweep run by hand | 2026-10-26 | **Passed.** Hold 37 (Ethan's House for "Testing", expiring 02:05 SGT): the 02:00 sweep sent the Coordinator `hold-expiring` (02:00:00.075); the 02:15 sweep made it Expired and sent `hold-expired` (02:15:00.108). It stays on the event's bookings and the venue's holds list as Expired, and the Coordinator's request answered 409 `hold-expired` |

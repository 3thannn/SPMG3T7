# Test Cases for US14.3: Place a Tentative Hold with an Expiry

> As a Venue Staff member, I want to place a tentative hold on a venue with an
> expiry date/time, so that I can keep a slot for a Coordinator who's still
> finalising, without blocking the venue forever.

## Acceptance Criteria

| # | Criterion |
| --- | --- |
| AC1 | A hold is a venue booking with status Held, linked to an event and its Coordinator |
| AC2 | Expiry date/time is required and must be in the future |
| AC3 | While Held and not expired, the slot counts as taken in US15.1 |
| AC4 | Coordinator can turn the hold into a booking request before it expires (status → Requested) |
| AC5 | A Held booking is never shown or counted as Confirmed |
| AC6 | Assumption: Venue Staff place holds (customer to confirm if Coordinators can too) |

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

**Team assumptions (not customer-confirmed), tested below:**
- A hold can be placed only for an event a Coordinator could request venues for: assigned to a Coordinator, and Approved or Planning (US14.1's rule).
- A hold must expire **no later than the booking starts**. Keeping a slot past the moment it is used means nothing.
- "Now" is Singapore local time, the same clock the booking and event times use.
- An expired hold is not rewritten. It stays Held, is flagged `holdExpired`, and stops counting as taken the moment it passes, so no scheduled job is needed. Notifying anyone about expiry is US14.4.
  - **Update (US14.4):** a pg_cron job now sweeps every 15 minutes, rewriting a lapsed hold to the new `Expired` status and notifying the Coordinator. The slot is still freed at the deadline by the rule above; the job only records it. An expired hold can no longer be cancelled. See `test_cases_us14_4.md`.
- Turning a hold into a request follows US14.1/US4.5: the first request moves an Approved event to Planning.
- The Coordinator can release a hold with the existing Cancel (US14.2).

**On AC3 and US15.1.** US15.1 (the availability check) is not on main yet. The "slot is taken" rule is the single `Booking.holds_venue` check, which US9.4's turnaround re-check already uses and US15.1 is documented to use. The test cases below check that rule directly and through US9.4's `find_conflicts`.

## Workflow Visualization

```
Venue Staff ──► Venue page ──► "Tentative holds" card
                 choose event (assigned, Approved/Planning) + start, end, expiry
                       │ POST /holds
                       ▼
           venue_bookings row: status Held, hold_expires_at, held_by_id
                       │
     ┌─────────────────┼───────────────────────────────┐
     ▼                 ▼                                ▼
 now < expiry      now ≥ expiry                  Coordinator cancels
 slot TAKEN        slot FREE, flagged expired     → Cancelled (released)
     │             (still Held, not Confirmed)
     ▼
 Coordinator on event page ──► "Request this venue"
   POST /events/{id}/bookings/{bookingId}/request
     ▼
 status Requested (event Approved → Planning) — waits for Venue Staff approval
```

## Test Files

| Layer | File |
| --- | --- |
| Backend | `backend/tests/test_venue_holds.py` (TC-H01–H55) |
| Frontend | `frontend/src/components/EventBookings.test.tsx` (TC-HF01–HF07), `frontend/src/holdsStore.test.ts` (TC-HF08–HF10, HF19–HF25, HF30), `frontend/src/components/VenueHolds.test.tsx` (TC-HF11–HF17, HF26–HF29, HF31), `frontend/src/pages/VenueDetailPage.test.tsx` (TC-HF18) |
| Database | Run against real PostgreSQL; see §6 |
| Updated for US14.3 | `test_booking_store.py` (cancel also matches Held), `test_venue_booking_cancellation.py` (Held is in `HOLDS_VENUE`), `test_venue_bookings.py` (three new response fields) |

---

## 1. HAPPY PATH TEST CASES

### TC-H01: Venue Staff place a hold (AC1, AC6)
- **Pre-conditions**: Event 900 "Faculty Welcome Night" is Approved and assigned to Coordinator Priya
- **Test Steps**: As Venue Staff (Sam), `POST /holds`
- **Test Data**:
  ```json
  {"venueId": "1", "eventId": "900", "startsAt": "2027-11-02T09:00",
   "endsAt": "2027-11-02T17:00", "expiresAt": "2027-10-08T17:00"}
  ```
- **Expected Result**: HTTP 201; `status` Held; `eventTitle` "Faculty Welcome Night"; `venueName` "Great Hall"; `holdExpiresAt` "2027-10-08T17:00"; `holdExpired` false; `heldByName` "Sam"
- **Automated**: `test_tc_h01_venue_staff_place_a_hold`

### TC-H02: The hold is stored as a booking nobody has requested yet (AC1)
- **Expected Result**: One booking, status Held, on event 900, `held_by_id` = Sam, `requested_by_id` null, headcount copied from the event's attendance
- **Automated**: `test_tc_h02_it_is_stored_as_a_booking_nobody_has_requested_yet`

### TC-H03: The event's Coordinator sees the hold on the event (AC1)
- **Expected Result**: `GET /events/900/bookings` as Priya lists Great Hall, status Held
- **Automated**: `test_tc_h03_the_events_coordinator_sees_it_on_the_event`, frontend TC-HF01

### TC-H05: A hold can be placed for a Planning event (AC1)
- **Automated**: `test_tc_h05_a_hold_can_be_placed_for_a_planning_event`

### TC-H27: The Coordinator turns the hold into a request (AC4)
- **Pre-conditions**: An unexpired hold on Great Hall for event 900
- **Test Steps**: As Priya, `POST /events/900/bookings/{id}/request`
- **Expected Result**: HTTP 200; `status` Requested; same times; `holdExpiresAt` kept as the record; `requested_by_id` = Priya; the slot is still taken
- **Automated**: `test_tc_h27_the_coordinator_requests_a_held_venue`, frontend TC-HF02

### TC-H28: The first request moves an Approved event to Planning (AC4, US4.5)
- **Automated**: `test_tc_h28_the_first_request_moves_an_approved_event_to_planning`

### TC-H29: A Planning event stays Planning (AC4)
- **Automated**: `test_tc_h29_a_planning_event_stays_planning`

### TC-H44: The Coordinator can release a hold (US14.2 Cancel)
- **Expected Result**: HTTP 200, status Cancelled, slot no longer taken
- **Automated**: `test_tc_h44_the_coordinator_can_release_a_hold`, frontend TC-HF07

### TC-H45: Venue Staff are offered only events that can take a hold (AC1)
- **Pre-conditions**: Events 901 Approved+assigned, 902 Planning+assigned, 903 no Coordinator, 904 Under Review, 905 Draft
- **Expected Result**: `GET /holds/events` returns 901 and 902 only, with the Coordinator's name
- **Automated**: `test_tc_h45_only_events_that_can_take_a_hold_are_offered`

### TC-H46: The venue lists its holds and flags expired ones
- **Expected Result**: `GET /holds?venueId=1` lists the two holds soonest first, the first flagged expired, and not the plain request
- **Automated**: `test_tc_h46_the_venue_lists_its_holds_and_flags_expired_ones`, frontend TC-HF11

### TC-HF13 / TC-HF14: Placing a hold from the venue page
- **Expected Result**: Choosing "Open Day — Priya" fills the start and end with the event's times; Place hold sends venue, event, times and expiry, then lists the hold with "Held for Open Day until …"
- **Automated**: `VenueHolds.test.tsx` › TC-HF13, TC-HF14

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-H04: Placing a hold does not move the event
- **Expected Result**: The event stays Approved; only a request moves it to Planning
- **Automated**: `test_tc_h04_placing_a_hold_does_not_move_the_event`

### TC-H40: A hold that expires between the check and the write is refused
- **Pre-conditions**: The store reports the hold expired at write time (the database function re-checks under a row lock)
- **Expected Result**: HTTP 409, reason `hold-expired`
- **Automated**: `test_tc_h40_expiring_between_the_check_and_the_write_is_refused`

### TC-H49 to TC-H51: The Supabase store
- **Expected Result**: `place_hold` inserts status Held with the expiry and Venue Staff id and no requester; `request_hold` calls `request_held_booking` with the event's expected status; the function's `expired`, `stale-event` and `not-held` answers each become their own error
- **Automated**: `test_tc_h49_…`, `test_tc_h50_…`, `test_tc_h51_…`

### TC-HF18: Only Venue Staff see the Tentative holds card
- **Automated**: `VenueDetailPage.test.tsx` › TC-HF18

### TC-H53 / TC-H54: Something changes between the check and the write
- **Expected Result**: A hold released in between → 409 "This hold has been cancelled."; an event that moves in between → 409 "This event changed while you were working on it. Refresh it and try again." and the hold stays Held
- **Automated**: `test_tc_h53_…`, `test_tc_h54_…`, `test_tc_h55_the_store_rechecks_the_hold_itself`

### TC-HF19 to TC-HF25: The frontend's API calls
- **Expected Result**: `GET /holds/events`, `GET /holds?venueId=1` and `POST /holds` (venue id plus the form values) with the session token; `POST /events/900/bookings/101/request`; a 400, 403 or 409 becomes a sentence on the page; a 401 is passed on so the session ends
- **Automated**: `holdsStore.test.ts` › TC-HF19–HF25

### TC-HF26, TC-HF27, TC-HF29: The holds card when something fails
- **Expected Result**: Holds that cannot load say so and the form still works; events that cannot load say so and the form stays shut; an unexpected failure placing a hold shows "Could not place this hold…"
- **Automated**: `VenueHolds.test.tsx` › TC-HF26, HF27, HF29

---

## 3. NEGATIVE TEST CASES

### TC-H06: Only Venue Staff place holds (AC6)
- **Expected Result**: Coordinator, Organiser and Coordinator Lead get HTTP 403
- **Automated**: `test_tc_h06_only_venue_staff_place_holds`

### TC-H07: An event with no Coordinator cannot be held for (AC1)
- **Expected Result**: HTTP 409, reason `no-coordinator`
- **Automated**: `test_tc_h07_an_event_with_no_coordinator_cannot_be_held_for`

### TC-H08: Only an event that can take bookings can be held for
- **Expected Result**: Submitted / Under Review → 409 `not-approved`; Rejected / Cancelled → 409 `event-closed`
- **Automated**: `test_tc_h08_only_an_event_that_can_take_bookings_can_be_held_for`

### TC-H09 / TC-H10: A bad hold is refused with a sentence
- **Expected Result**: HTTP 400 naming the first problem: no venue, unknown venue, no event, unknown or Draft event, no start, end before start, impossible date
- **Automated**: `test_tc_h09_a_bad_hold_is_refused_with_a_sentence`, `test_tc_h10_a_draft_event_is_not_offered`

### TC-H11 to TC-H15: Expiry is required and in the future (AC2)
- **Expected Result**: Missing or blank → "Give the hold an expiry date and time."; not `YYYY-MM-DDTHH:MM` → "Give the expiry as YYYY-MM-DDTHH:MM."; impossible date → "… is not a real date and time."; in the past → "The hold must expire in the future."
- **Automated**: TC-H11–H15; frontend TC-HF09, TC-HF15

### TC-H18: Expiry after the booking starts is refused
- **Expected Result**: "The hold must expire no later than the booking starts."
- **Automated**: `test_tc_h18_expiry_after_the_booking_starts_is_refused`

### TC-H30: An expired hold cannot be requested (AC4)
- **Expected Result**: HTTP 409, reason `hold-expired`, message "The hold on Great Hall expired at 2027-10-08 17:00. Ask Venue Staff to hold it again, or request the venue as a new booking."; the booking stays Held
- **Automated**: `test_tc_h30_an_expired_hold_cannot_be_requested`, frontend TC-HF03, TC-HF04

### TC-H32 to TC-H34: Only an active hold can be requested
- **Expected Result**: Requesting twice → "This hold has already been turned into a booking request."; after release → "This hold has been cancelled."; a plain request → 409 `not-held`
- **Automated**: TC-H32, H33, H34

### TC-H35 to TC-H39: Who may request it, and on what
- **Expected Result**: Another Coordinator → 404; Venue Staff and Organiser → 403; a hold on another event or an unknown id → 404; a Cancelled event → 409 `event-closed`
- **Automated**: TC-H35–H39; frontend TC-HF05, TC-HF06

### TC-H52: An unreadable expiry counts as expired
- **Expected Result**: The hold is flagged expired and does not keep the slot; a hold must never block a venue longer than anyone agreed to
- **Automated**: `test_tc_h52_an_unreadable_expiry_counts_as_expired`

### TC-H47 / TC-H48: Listing holds
- **Expected Result**: A missing or non-numeric venue id → 400; a Coordinator → 403 on both list routes
- **Automated**: TC-H47, TC-H48

---

## 4. BOUNDARY TEST CASES

All with "now" pinned to 2027-10-01 09:00.

| Case | Input | Expected | Automated |
| --- | --- | --- | --- |
| TC-H16 | expiry = now (09:00) | Refused: must be in the future | `test_tc_h16_…` |
| TC-H17 | expiry = now + 1 min (09:01) | Accepted | `test_tc_h17_…` |
| TC-H19 | expiry = booking start | Accepted | `test_tc_h19_…` |
| TC-H18 | expiry = start + 1 min | Refused | `test_tc_h18_…` |
| TC-H20 | start in the past | Refused: "A hold cannot start in the past." | `test_tc_h20_…` |
| TC-H23 | now = expiry − 1 min | Still holds the slot | `test_tc_h23_…` |
| TC-H22 | now = expiry | Slot freed, flagged expired, still Held | `test_tc_h22_…` |
| TC-H31 | request at expiry − 1 min | Accepted | `test_tc_h31_…` |
| TC-H30 | request at expiry | Refused `hold-expired` | `test_tc_h30_…` |
| TC-HF10 | form: expiry now + 1 min, and = start | Accepted | `holdsStore.test.ts` |
| TC-HF28 | form: times edited after choosing the event | The edited times are sent | `VenueHolds.test.tsx` |
| TC-HF31 | a hold placed before an existing later one | Listed first | `VenueHolds.test.tsx` |

### AC3: The slot counts as taken
| Case | Expected | Automated |
| --- | --- | --- |
| TC-H21 | An unexpired hold `holds_venue` | `test_tc_h21_…` |
| TC-H24 | A hold and a request for the same slot are a conflict (US9.4 `find_conflicts`) | `test_tc_h24_…` |
| TC-H25 | Once the hold expires, the same pair is no conflict | `test_tc_h25_…` |
| TC-H26 | The event's booking list flags an expired hold | `test_tc_h26_…` |

### AC5: Never Confirmed
| Case | Expected | Automated |
| --- | --- | --- |
| TC-H41 | Venue Staff cannot approve a hold straight to Confirmed (US16.1): it must be requested first | `test_tc_h41_…` |
| TC-H42 | A hold reads "Held" before expiry, at expiry, and after the event date | `test_tc_h42_…` |
| TC-H43 | A requested hold is Requested, not Confirmed | `test_tc_h43_…` |
| TC-HF01 | The event page never shows "Confirmed" for a hold | `EventBookings.test.tsx` |

---

## 5. TRACEABILITY MATRIX

| AC | Test cases | Status |
| --- | --- | --- |
| AC1 Held booking linked to event and Coordinator | TC-H01–H10, H45, HF01, HF11–HF14 | ✅ |
| AC2 Expiry required and in the future | TC-H11–H20, H52, HF08–HF10, HF15; database checks | ✅ |
| AC3 Slot taken while Held and not expired | TC-H21–H26 | ✅ through `holds_venue`, used by US9.4 today and US15.1 once built |
| AC4 Coordinator turns hold into a request | TC-H27–H40, H53–H55, HF02–HF07, HF24, HF25; database checks | ✅ |
| AC5 Never shown or counted as Confirmed | TC-H41–H43, HF01, HF03 | ✅ |
| AC6 Venue Staff place holds | TC-H06, H36, H48, HF18 | ✅ |

## 6. TEST EXECUTION RESULTS

| Run | Date | Result |
| --- | --- | --- |
| Backend `ruff check`, `compileall`, `pytest` | 2026-10-16 | 1293 passed (75 in `test_venue_holds.py`) |
| Frontend `lint`, `tsc`, `build`, `vitest` | 2026-10-16 | 748 passed (40 for US14.3) |
| Coverage, `app/holds.py` | 2026-10-16 | 100% |
| Coverage, US14.3 lines in `booking_store.py` and `events.py` | 2026-10-16 | 100% (the only uncovered lines belong to US14.1/US4.5) |
| Coverage, `holdsStore.ts`, `VenueHolds.tsx` | 2026-10-16 | 100% of lines |

### Database verification against real PostgreSQL (2026-10-16)
The shared Supabase project did not have the migration yet, so the SQL was
run on a throwaway local PostgreSQL built from main's `SUPABASE_SETUP.sql`
and main's migrations in README order. 19 of 19 checks passed:

| Check | Result |
| --- | --- |
| `SUPABASE_ADD_VENUE_HOLDS.sql` applies on top of main's schema, and again (idempotent) | ✅ |
| `booking_status` gains Held | ✅ Requested, Cancelled, Held |
| Active hold → `requested`; booking Requested by the Coordinator; Approved event → Planning; status change recorded | ✅ |
| Requesting it again → `not-held` | ✅ |
| Planning event → `requested`, stays Planning, no status change written | ✅ |
| Expired hold → `expired`; booking stays Held; event unchanged | ✅ |
| Another Coordinator, an event that moved, or a closed event → `stale-event`; nothing written | ✅ |
| Unknown booking → `not-held` | ✅ |
| A Held booking with no expiry is refused by `venue_bookings_hold_has_expiry` | ✅ |
| A hold can be cancelled (released), and is then `not-held` | ✅ |
| Removing the Venue Staff user keeps the hold (`held_by_id` set null) | ✅ |
| Only `service_role` may call `request_held_booking`; `anon` and `authenticated` may not | ✅ |
| The updated `SUPABASE_SETUP.sql` builds a fresh database with the hold columns | ✅ |

### API walkthrough (2026-10-16)
Through the real routes and sign-in, with in-memory storage and the clock
pinned: Venue Staff are offered only assigned Approved/Planning events; a
missing, past, or after-start expiry and an event with no Coordinator are
refused; a Coordinator cannot place a hold; two holds are placed and both
take the slot (one clash under US9.4's rule); when one expires it frees the
slot (no clash) and is flagged expired; the Organiser cannot request a hold;
the Coordinator requests the active one (Requested, event → Planning), cannot
request it twice, and cannot request the expired one; no booking is ever
Confirmed.

### Live verification against the shared Supabase project (2026-10-16)
After running `SUPABASE_ADD_VENUE_HOLDS.sql` (booking_status: Requested,
Cancelled, Held), through the running app as the real accounts, on event 30
(Planning, Coordinator Ethan) at Ethan's House, June 2027 slots:

| Step | Result |
| --- | --- |
| No expiry / expiry in the past | HTTP 400 with the sentence |
| Coordinator places a hold | HTTP 403 |
| Venue Staff place hold A | HTTP 201, Held, held by Sam, expires in a day |
| Coordinator sees it on event 30 | Listed as Held |
| Organiser requests it | HTTP 403 |
| Coordinator requests hold A | HTTP 200, Requested; event stays Planning |
| Requests it again | HTTP 409 "already been turned into a booking request" |
| Hold C placed, then released with Cancel | HTTP 200 Cancelled; requesting it → 409 "has been cancelled" |
| Hold B placed to expire 2 minutes later | Not flagged before; flagged `holdExpired` after |
| Coordinator requests expired hold B | HTTP 409 "expired at 2026-10-16 22:57" |
| `request_held_booking` called on hold B directly | `'expired'`: Postgres's Singapore clock agrees with the API's |
| Bookings made before US14.3 (events 18, 30) | Still load, HTTP 200, with empty hold fields |

The three test bookings were deleted afterwards.

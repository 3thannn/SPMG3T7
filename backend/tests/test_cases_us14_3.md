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
| Backend | `backend/tests/test_venue_holds.py` (TC-H01–H51) |
| Frontend | `frontend/src/components/EventBookings.test.tsx` (TC-HF01–HF07), `frontend/src/holdsStore.test.ts` (TC-HF08–HF10), `frontend/src/components/VenueHolds.test.tsx` (TC-HF11–HF17), `frontend/src/pages/VenueDetailPage.test.tsx` (TC-HF18) |
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
| TC-H41 | There is no Confirmed booking status at all | `test_tc_h41_…` |
| TC-H42 | A hold reads "Held" before expiry, at expiry, and after the event date | `test_tc_h42_…` |
| TC-H43 | A requested hold is Requested, not Confirmed | `test_tc_h43_…` |
| TC-HF01 | The event page never shows "Confirmed" for a hold | `EventBookings.test.tsx` |

---

## 5. TRACEABILITY MATRIX

| AC | Test cases | Status |
| --- | --- | --- |
| AC1 Held booking linked to event and Coordinator | TC-H01–H10, H45, HF01, HF11–HF14 | ✅ |
| AC2 Expiry required and in the future | TC-H11–H20, HF08–HF10, HF15 | ✅ |
| AC3 Slot taken while Held and not expired | TC-H21–H26 | ✅ through `holds_venue`, used by US9.4 today and US15.1 once built |
| AC4 Coordinator turns hold into a request | TC-H27–H40, HF02–HF07 | ✅ |
| AC5 Never shown or counted as Confirmed | TC-H41–H43, HF01, HF03 | ✅ |
| AC6 Venue Staff place holds | TC-H06, H36, H48, HF18 | ✅ |

## 6. TEST EXECUTION RESULTS

| Run | Date | Result |
| --- | --- | --- |
| Backend `ruff check`, `compileall`, `pytest` | 2026-10-15 | 1288 passed (70 in `test_venue_holds.py`) |
| Frontend `lint`, `tsc`, `build`, `vitest` | 2026-10-15 | 733 passed (25 for US14.3) |

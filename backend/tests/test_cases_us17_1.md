# Test Cases for US17.1: Safety Officer Review Queue

> As a Safety Officer, I want to see events waiting for a safety check with
> everything I need to review them, so that I can assess them without chasing
> people for info.

## Acceptance Criteria

| # | Criterion |
| --- | --- |
| AC1 | List shows events in Pending Safety Check, oldest first |
| AC2 | Detail view shows expected attendance, each booked venue's capacity, layout, accessibility and known restrictions, reserved equipment, and the event's accessibility requirements |
| AC3 | Read-only |
| AC4 | Safety Officer role only |

### Team assumptions (not customer-confirmed)
- **Oldest first** = longest waiting: ordered by when the event last entered Pending
  Safety Check (US4.4). An event sent back and re-sent joins the end.
- **Booked venue** = a booking that holds its venue (Confirmed; Requested or an
  unexpired hold cannot exist once US4.4 lets the event through). Cancelled, Rejected
  and expired bookings are not shown.
- **Known restrictions** = operating hours, setup/turnaround minutes (US9.4) and
  unavailability periods (US12.1) that have not ended yet, with their reasons.
- **Reserved equipment** = lines with status `Reserved` (US19.3). Until US19.3 ships the
  list is always empty — and US4.4 only lets an event through with no outstanding lines.
- **Read-only** covers the review itself. The approve / send-back controls on the same
  page belong to US4.4/US17.2.

## Test Files

| Layer | File |
| --- | --- |
| Backend | `backend/tests/test_safety_review_us17_1.py` |
| Frontend | `frontend/src/components/SafetyReviewDetails.test.tsx`, `frontend/src/eventsStore.test.ts` (US17.1 block), `frontend/src/pages/EventDetailPage.test.tsx` (US17.1 block), `frontend/src/pages/SafetyReviewPage.test.tsx` (queue page, from US4.4) |
| Database | None — no schema change |

---

## 1. HAPPY PATH

### TC-R01: The queue, oldest first (AC1)
- **Pre-conditions**: Pending events 1, 2, 3 entered the check on 3, 1 and 2 Jan; events 4–6 are Planning, Confirmed, Under Review
- **Test Steps**: `GET /events/safety-check` as the Safety Officer
- **Expected Result**: `[2, 3, 1]`, all Pending Safety Check; ties ordered by id; an empty queue is `[]`
- **Automated**: `TestQueue`; frontend `SafetyReviewPage.test.tsx`

### TC-R02: The event and its accessibility requirements (AC2)
- **Test Steps**: `GET /events/700/safety-review`
- **Expected Result**: expected attendance 30, accessibility requirements "Wheelchair access", preferred layout, venue requirements, times, waiting since
- **Automated**: `test_the_event_and_its_accessibility_requirements`; frontend "shows the expected attendance and the event accessibility requirements"

### TC-R03: Each booked venue (AC2)
- **Pre-conditions**: Riverside Hall — capacity 100, layouts "Theatre, Banquet", step-free access + hearing loop, 08:00–22:00, setup 30 / turnaround 45; booking for 30 people, Theatre, needs hearing loop
- **Expected Result**: all of the above returned and shown; `overCapacity` false
- **Automated**: `test_each_booked_venue_with_capacity_layout_and_accessibility`; frontend "shows capacity, layout, accessibility and known restrictions"

### TC-R04: Known restrictions (AC2)
- **Pre-conditions**: closures ended 10 days ago, in 5–6 days ("Fire alarm testing"), in 30–32 days ("Renovation"), and one on another venue
- **Expected Result**: only the two not yet over, soonest first, with reasons
- **Automated**: `test_known_restrictions_include_closures_not_yet_over`, `test_a_closure_ending_today_still_restricts`

### TC-R05: Reserved equipment (AC2)
- **Pre-conditions**: lines Reserved, Removed, and Reserved on another event
- **Expected Result**: only this event's Reserved line, with type, quantity, time and notes
- **Automated**: `test_only_reserved_equipment_is_listed`, `TestReservedEquipmentStore`; frontend "shows each line with its quantity, time and notes"

### TC-R06: Several venues, only the booked ones (AC2)
- **Pre-conditions**: Riverside Hall and a Breakout Room for 25 (capacity 20), plus Cancelled, Rejected and expired-hold bookings
- **Expected Result**: the two booked venues in booking order; the Breakout Room flagged over capacity and highlighted on the page
- **Automated**: `test_several_venues_and_only_the_ones_actually_booked`; frontend "warns when more people are booked in than the venue holds"

## 2. NEGATIVE AND BOUNDARY

| ID | Scenario | Expected | Automated |
| --- | --- | --- | --- |
| TC-R10 | Organiser, Coordinator, Lead, Venue Staff, Tech Support | 403 for the review and the queue (AC4) | `test_every_other_role_is_refused` |
| TC-R11 | Not signed in | 401 | `test_signed_out_is_refused` |
| TC-R12 | Safety Officer, event Planning / Confirmed / Draft | 404 | `test_only_while_the_event_waits_for_them` |
| TC-R13 | Unknown or non-numeric id | 404 | `test_an_unknown_event` |
| TC-R14 | POST / PUT / PATCH / DELETE on the review | 405 (AC3) | `test_the_review_accepts_no_writes` |
| TC-R15 | Reading changes nothing | events and bookings unchanged (AC3) | `test_reading_the_review_changes_nothing` |
| TC-R16 | Page offers no buttons or inputs in the review | none (AC3) | frontend "offers nothing to edit or press" |
| TC-R17 | Headcount = capacity / capacity + 1 / either unknown | not over / over / not over | `test_over_capacity_boundary` |
| TC-R18 | Venue record has gone | booking still shown, capacity "Unknown" | `test_a_venue_record_that_has_gone_still_shows_the_booking`; frontend "says what a venue has not recorded" |
| TC-R19 | No venues, no equipment, nothing stated | "No venue is booked…", "No equipment is reserved…", "Not stated" | `test_no_equipment_and_no_venues_are_answered_as_empty`; frontend "says what was not given" |
| TC-R20 | Review cannot be loaded | "Could not load the safety review…" | frontend "says when the review cannot be loaded" |
| TC-R21 | Only the Safety Officer's event page loads the review | Coordinator never sees it | frontend "shows no safety review to anyone else" |

# Test Cases for US14.1, US14.2, US18.1: Venue Bookings, Cancelling One, and Suitability

> **US14.1** As an Event Coordinator, I want to request one or more venues for an
> event, so that a bigger event can use a main hall and its breakout rooms at once.
>
> **US14.2** As an Event Coordinator, I want to cancel a single venue booking with a
> reason, so that one room can change without redoing the whole plan.
>
> **US18.1** As an Event Coordinator, I want to see whether a venue suits a booking
> before I request it, so that I don't request a room that cannot work.

## Acceptance Criteria

| # | Criterion | Status |
| --- | --- | --- |
| US14.1 AC1 | A booking is its own record: the assigned Coordinator requests one venue, with a start and an end, for an event | Done |
| US14.1 AC2 | A venue already stored on the event is moved into a booking | Nothing to move: `events` never had a venue column |
| US14.1 AC3 | One event can have many bookings, and each stands on its own | Done — a refused request never blocks another |
| US14.1 AC4 | Every booking for the event shows together on the event page | Done — for the owning Organiser and the assigned Coordinator |
| US14.1 AC5 | A new booking starts Requested and waits for Venue Staff | Done |
| US14.1 AC6 | Only the assigned Coordinator requests (US8.6) | Done |
| US14.2 AC1 | Cancelling sets the booking to Cancelled; a reason is required; who and when are kept | Done |
| US14.2 AC2 | The event's other bookings are unchanged | Done |
| US14.2 AC3 | The event's status is unchanged | Done |
| US14.2 AC4 | A cancelled booking no longer holds the venue for its slot | Done |
| US18.1 AC1 | Each booking has its own headcount, defaulting to the event's expected attendance | Done |
| US18.1 AC2 | Picking a venue shows Suitable or Not suitable, with every reason | Done |
| US18.1 AC3 | Not suitable when: the headcount is over capacity (equal is fine), the layout is not supported, a facility or accessibility need is not listed, or the booking is outside operating hours | Done |
| US18.1 AC4 | A venue that is not suitable cannot be requested | Done — 409 `not-suitable` with the same reasons |

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

### Team assumptions (not customer-confirmed)
- **One request is one booking.** A main hall and two breakout rooms are three
  requests, so a refused room never takes another with it.
- **Venues can be requested only for Approved and Planning events.** The first
  request moves Approved to Planning. Submitted and Under Review answer
  `not-approved`; Confirmed, Rejected, Cancelled and Completed answer
  `event-closed`.
- **Booking times are Singapore local times** and need not match the event's own
  (a breakout room may be wanted for the afternoon only). The start may not be on a
  past date; a time earlier today is allowed.
- **Who.** The `bookings:request` permission admits the Coordinator role; the
  event's assignment admits the Coordinator. Anyone else gets 404, the same answer
  US8.1 gives for the event itself.
- **A cancelled booking is kept** on the event, with who cancelled it, when and why.
  A booking on a Completed or Rejected event can still be cancelled, which is how
  the venue is given back. A Cancelled event is read-only (US4.6).
- **Suitability is a pure rule** (`app/suitability.py`, no I/O). The check route
  stores nothing; the request route runs the same check. Hours that are not
  recorded, or cannot be read, are noted rather than held against the venue.

## Workflow Visualization

```
Assigned Coordinator, event Approved or Planning
   │ picks a venue, times, headcount (default: event attendance), needs
   ▼
POST /events/{id}/bookings/suitability ──► Suitable / Not suitable + reasons (stores nothing)
   │
POST /events/{id}/bookings
   ├─ not suitable ─────────────► 409 not-suitable (same reasons)
   ├─ bad venue / times ────────► 400 invalid_booking (one sentence)
   ├─ wrong status ─────────────► 409 not-approved / event-closed
   └─ ok ──► 201 Requested (Approved event → Planning)
                │
GET /events/{id}/bookings ──► every booking, soonest first (Organiser + assigned Coordinator)
                │
POST /events/{id}/bookings/{bookingId}/cancel {"reason": "..."}
   ├─ no reason / > 2000 chars ─► 400
   ├─ already cancelled ────────► 409 already-cancelled
   └─ ok ──► Cancelled (who, when, why); other bookings and the event untouched;
             the venue's slot is free again
```

## Test Files

| Layer | File |
| --- | --- |
| Backend | `test_venue_bookings.py` (US14.1), `test_venue_booking_cancellation.py` (US14.2), `test_venue_suitability.py` (US18.1 routes), `test_suitability.py` (US18.1 rule), `test_booking_store.py` (the Supabase store's queries) |
| Frontend | `EventBookings.test.tsx` (tests without a `TC-` prefix are these stories; `TC-HF`, `TC-DF`, `TC-CF` and `TC-FF` belong to US14.3, US16.1, US15.1 and US15.2), `eventsStore.test.ts` ("US18.1: the booking form as the API reads it") |
| Database | `SUPABASE_ADD_VENUE_BOOKINGS.sql`, `SUPABASE_CANCEL_VENUE_BOOKINGS.sql`, `SUPABASE_ADD_BOOKING_NEEDS.sql` (run in that order) |

---

## 1. HAPPY PATH TEST CASES

### US14.1 — Requesting venues

#### TC-B01: The assigned Coordinator requests a venue (AC1, AC5)
- **Pre-conditions**: Event Approved, assigned to the Coordinator
- **Test Steps**: `POST /events/{id}/bookings` with `{"venueId": "1", "startsAt": "2027-11-02T09:00", "endsAt": "2027-11-02T17:00"}`
- **Expected Result**: 201; status Requested; stored against the event and the venue, with who requested it
- **Automated**: `test_the_assigned_coordinator_requests_a_venue`, `test_a_new_booking_is_requested_and_waits_for_venue_staff`, `test_the_booking_is_stored_against_the_event_and_the_venue`, `test_the_record_keeps_who_requested_it`; frontend "requests the chosen venue and adds it to the list as Requested"

#### TC-B02: Several venues for one event (AC1, AC3)
- **Expected Result**: three requests make three bookings; the same venue may be booked twice; a refused request leaves the earlier ones untouched
- **Automated**: `test_an_event_can_have_several_venues`, `test_the_same_venue_can_be_booked_twice_for_one_event`, `test_a_refused_booking_does_not_block_the_others`, `test_a_refused_booking_leaves_an_earlier_one_untouched`; frontend "requests several venues for one event, one after another", "shows a refusal without touching the bookings already made"

#### TC-B03: The bookings show on the event page (AC4)
- **Expected Result**: every booking with its venue, times and status, soonest first, for the owning Organiser and the assigned Coordinator; the card says so when there are none
- **Automated**: `test_a_stored_booking_reads_back`, `test_bookings_come_back_soonest_first`, `test_the_owning_organiser_sees_the_bookings`, `test_no_bookings_is_an_empty_list`; frontend "lists every booking for the event with its venue, times and status", "says so when no venue has been requested yet", "keeps the list sorted by time when a booking is added"

#### TC-B04: Both open statuses take requests (AC1)
- **Expected Result**: Approved and Planning → 201
- **Automated**: `test_an_open_event_takes_requests` (parametrised)

#### TC-B05: The whole journey
- **Automated**: `test_the_whole_journey_through_the_routes`

### US14.2 — Cancelling one booking

#### TC-BC01: The assigned Coordinator cancels a booking (AC1)
- **Test Steps**: `POST /events/{id}/bookings/{bookingId}/cancel` with `{"reason": "Numbers dropped, so the hall is too big."}`
- **Expected Result**: 200; status Cancelled; who, when and the trimmed reason kept on the booking; everything else about it unchanged; it stays on the event
- **Automated**: `test_the_assigned_coordinator_cancels_a_booking`, `test_who_when_and_why_are_kept_on_the_booking`, `test_the_cancellation_is_stored`, `test_the_cancelled_booking_stays_on_the_event`, `test_everything_but_the_status_and_cancellation_is_as_it_was`; frontend "cancels the one booking with the reason, and shows who, when and why"

#### TC-BC02: The other bookings are unchanged (AC2)
- **Automated**: `test_only_the_cancelled_booking_changes`, `test_bookings_on_other_events_are_untouched`; frontend "leaves the other bookings exactly as they were"

#### TC-BC03: The event is unchanged (AC3)
- **Expected Result**: an Approved or Planning event keeps its status, even when its last booking is cancelled
- **Automated**: `test_the_event_status_is_unchanged` (parametrised), `test_cancelling_the_last_booking_still_leaves_the_event_alone`

#### TC-BC04: The venue's slot is free again (AC4)
- **Expected Result**: a Requested booking holds the venue, a Cancelled one does not; the same venue and slot can be requested again
- **Automated**: `test_a_requested_booking_holds_the_venue`, `test_a_cancelled_booking_does_not`, `test_only_requested_held_and_confirmed_can_hold_a_venue`, `test_the_same_venue_and_slot_can_be_requested_again`

#### TC-BC05: The Organiser sees who cancelled, when and why (AC1)
- **Expected Result**: "Cancelled by Priya, 08 Oct 2026, 18:00: <reason>" (the stored UTC time shown in Singapore time); "a former user" when the canceller's account is gone
- **Automated**: `test_the_owning_organiser_sees_who_cancelled_and_why`; frontend "shows a cancelled booking from the server with who, when and why", "still shows the reason when the user who cancelled has been removed"

### US18.1 — Suitability

#### TC-SU01: Each booking has its own headcount (AC1)
- **Expected Result**: left out, it is the event's attendance; given, it is the booking's own; a breakout room is checked against its own headcount, not the whole event
- **Automated**: `test_left_out_it_is_the_events_attendance`, `test_a_booking_can_give_its_own`, `test_a_breakout_room_is_not_checked_against_the_whole_event`, `test_the_check_uses_the_same_default`; frontend "starts the headcount at the event attendance"

#### TC-SU02: Picking a venue shows the verdict (AC2)
- **Test Steps**: `POST /events/{id}/bookings/suitability` with the venue, times, headcount and needs
- **Expected Result**: `{"suitable": true, "reasons": [], "notes": []}` or `false` with every reason; nothing is stored; the page says Suitable or Not suitable as soon as a venue is picked
- **Automated**: `test_a_suitable_venue`, `test_a_venue_that_is_not_suitable_says_why`, `test_checking_stores_nothing`; frontend "checks a venue as soon as it is picked, and says Suitable", "says Not suitable with the reasons, and will not request it", "checks again with the booking's own headcount"

#### TC-SU03: Each condition in the rule (AC3)
- **Expected Result**: over capacity names both numbers ("It holds 60 people, and this booking is for 61."); a layout not supported names the ones that are; each missing facility or accessibility need is its own reason; outside the hours, overnight or on a closed day is not suitable; all reasons are listed in the story's order
- **Automated**: `TestCapacity`, `TestLayout`, `TestFacilitiesAndAccessibility`, `TestOperatingHours`, `TestEveryReasonAtOnce`; through the route: `test_a_layout_it_does_not_support`, `test_a_missing_facility_and_accessibility_need`, `test_a_time_outside_its_hours`

#### TC-SU04: A venue that is not suitable cannot be requested (AC4)
- **Expected Result**: 409 `not-suitable` with the same reasons the check showed; nothing stored; another, suitable venue can still be requested
- **Automated**: `test_one_over_capacity_is_refused`, `test_outside_its_hours_is_refused`, `test_the_refusal_gives_the_same_reasons_the_check_showed`, `test_an_unsuitable_venue_does_not_block_another`; frontend "shows a refusal when the server finds the venue unsuitable at request time"

#### TC-SU05: What the booking needs is kept and shown
- **Expected Result**: layout, facilities and accessibility needs are stored and shown on the booking; a comma-separated list is read as a list; a need named twice is kept once
- **Automated**: `TestWhatABookingNeedsIsKept`, `TestSupabaseCreateNeeds`; frontend "sends what the booking needs with the request", "says what each booking was made for"

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-B10: Each role sees only what it may use
- **Expected Result**: the Organiser sees the bookings but no request form and no Cancel; Cancel is offered only on a Requested booking; a booking already cancelled has no Cancel
- **Automated**: frontend "does not offer the Organiser the form or load the catalogue for them", "offers the Coordinator a cancel for each Requested booking", "offers the Organiser no cancel", "offers no cancel on a booking that is already cancelled"

### TC-B11: The page checks before it sends
- **Expected Result**: no venue, an end not after the start, or a headcount of 0 is caught in the page; times start from the event's own, and the venue is cleared after a request while the times are kept
- **Automated**: frontend "asks for a venue before sending anything", "refuses an end that is not after the start before sending anything", "refuses a headcount of nobody before sending anything", "offers the Coordinator the catalogue, starting from the event times", "clears the venue after a request but keeps the times for the next one", "does not check while the form would be refused anyway"

### TC-B12: Cancelling asks for a reason, and backs out cleanly
- **Expected Result**: the reason box opens under the booking being cancelled; "Keep booking" closes it and cancels nothing; a refused cancel keeps the box and the reason
- **Automated**: frontend "asks for a reason under the booking being cancelled", "keeps the booking when the Coordinator changes their mind", "keeps the box open with the reason when the cancel is refused", "explains an unexpected failure to cancel"

### TC-B13: Rules are checked in a fixed order
- **Expected Result**: who may see the event, then its status, then the request body; for a cancel, the booking's status before the reason
- **Automated**: `test_visibility_is_checked_before_the_status`, `test_the_status_is_checked_before_the_body`, `test_the_status_is_checked_before_the_reason`

### TC-B14: The Supabase store asks for the right rows
- **Expected Result**: bookings for one event, soonest first with stable ties, with the venue name; a cancel is one conditional update of one row, never another table
- **Automated**: `TestSupabaseListing`, `TestSupabaseCreate`, `TestSupabaseCancel`, `TestCancellationColumns`, `TestInMemory`

### TC-B15: Booking times read clearly
- **Expected Result**: a booking within one day shows the end time only; one past midnight shows both dates
- **Automated**: frontend "shows only the end time when a booking is within one day", "shows both dates in full when a booking runs past midnight"

---

## 3. NEGATIVE TEST CASES

| ID | Scenario | Expected | Automated |
| --- | --- | --- | --- |
| TC-B20 | The Organiser or Venue Staff request a venue | 403 | `test_the_owning_organiser_cannot_request`, `test_venue_staff_cannot_request`, `test_only_the_coordinator_role_holds_the_permission` |
| TC-B21 | A Coordinator the event is not assigned to; an event with no Coordinator | 404 | `test_a_coordinator_not_assigned_to_the_event_cannot_request`, `test_an_unassigned_event_cannot_have_venues_requested`, `test_a_coordinator_not_assigned_to_the_event_does_not_see_them` |
| TC-B22 | Venue Staff read an event's bookings; another Organiser's event | 403 / 404 | `test_venue_staff_cannot_read_an_events_bookings`, `test_another_organisers_event_is_not_found` |
| TC-B23 | Request for a Confirmed, Rejected, Cancelled or Completed event | 409 `event-closed`, "This event is closed, so no more venues can be requested for it."; its bookings still show | `test_a_closed_event_is_refused_with_the_reason`, `test_a_closed_event_still_shows_the_bookings_it_had`, `test_the_rule_on_its_own` |
| TC-B24 | Request for a Draft (as a Coordinator) | 404 | `test_a_draft_is_not_found_by_a_coordinator` |
| TC-B25 | No venue, or a blank one | 400 `invalid_booking`, "Choose a venue." | `test_a_venue_is_required`, `test_a_blank_venue_is_no_venue`, `test_the_venue_is_named_first` |
| TC-B26 | A venue not in the catalogue, or an id that is not an id | 400, "That venue is not in the catalogue." | `test_a_venue_not_in_the_catalogue_is_refused`, `test_a_venue_id_that_is_not_an_id_is_refused` |
| TC-B27 | No start or no end; another format; an impossible date or time | 400, e.g. "Give the booking a start time." | `test_a_start_is_required`, `test_an_end_is_required`, `test_a_start_in_another_format_is_refused`, `test_an_impossible_date_is_refused`, `test_an_impossible_time_is_refused` |
| TC-B28 | End before the start | 400, "The booking must end after it starts." | `test_an_end_before_the_start_is_refused` |
| TC-B29 | Unknown event; an event id that is not a number; signed out | 404 / 404 / 401 | `test_a_missing_event_is_not_found`, `test_a_non_numeric_event_id_is_not_found`, `test_a_signed_out_caller_is_asked_to_sign_in` |
| TC-BC20 | Cancel with no reason, or only spaces | 400 `invalid_booking`, "Give a reason for cancelling this booking."; unchanged | `test_a_reason_is_required`, `test_a_blank_reason_is_no_reason` |
| TC-BC21 | Cancel twice; lose a race to another cancel | 409 `already-cancelled`; the first cancellation is kept | `test_a_second_cancel_is_refused_with_the_reason`, `test_the_first_cancellation_is_kept`, `test_losing_a_race_to_another_cancel_is_refused_not_crashed` |
| TC-BC22 | The Organiser or Venue Staff cancel; a Coordinator no longer assigned | Refused; 404 for the Coordinator | `test_the_owning_organiser_cannot_cancel`, `test_venue_staff_cannot_cancel`, `test_a_coordinator_no_longer_assigned_cannot_cancel` |
| TC-BC23 | A booking that is not there, or on another event | 404 `booking_not_found` | `test_a_booking_that_is_not_there_is_not_found`, `test_a_non_numeric_booking_id_is_not_found`, `test_a_booking_on_another_event_is_not_found_through_this_one` |
| TC-BC24 | Cancel a booking on a Cancelled event | 409 `event-cancelled` (US4.6) | `test_a_cancelled_event_is_read_only` |
| TC-SU20 | The Organiser, Venue Staff or an unassigned Coordinator checks; a closed event; a venue not in the catalogue; signed out | Refused like a request | `TestTheCheckIsRefusedLikeARequest` |
| TC-SU21 | An event with no attendance and no headcount given | 400, "Give the headcount for this booking. …" | `test_an_event_with_no_attendance_needs_a_headcount_given`; frontend "leaves the headcount for the Coordinator when the event has no attendance" |
| TC-SU22 | Headcount -5, `"abc"` or `"1.5"` | 400 `invalid_booking`, "Give the headcount as a whole number of people." | `test_a_headcount_that_is_not_a_count_of_people` (parametrised) |
| TC-SU23 | A need over 100 characters, an overlong layout, more than 20 needs | 400 | `test_an_overlong_need_is_refused`, `test_an_overlong_layout_is_refused`, `test_too_many_needs_are_refused` |

## 4. BOUNDARY TEST CASES

| ID | Boundary | Expected | Automated |
| --- | --- | --- | --- |
| TC-B30 | End equal to the start | 400 (a booking of no length) | `test_an_end_equal_to_the_start_is_refused` |
| TC-B31 | Start earlier today / on yesterday's date | Accepted / 400 "A booking cannot start in the past." | `test_a_booking_starting_today_is_accepted`, `test_a_start_in_the_past_is_refused` |
| TC-B32 | Times with seconds; spaces around values; a venue id sent as a number | Accepted | `test_times_with_seconds_are_accepted`, `test_values_are_trimmed_before_they_are_read`, `test_a_venue_id_sent_as_a_number_is_accepted` |
| TC-BC30 | Cancel reason over 2,000 characters | 400 | `test_an_overlong_reason_is_refused` |
| TC-BC31 | Cancel on a Completed or Rejected event | Allowed (gives the venue back) | `test_a_booking_on_a_closed_event_can_still_be_cancelled` (parametrised); frontend "still offers a cancel on a closed event, to give the venue back" |
| TC-SU30 | Headcount equal to capacity / one over | Suitable / Not suitable | `test_headcount_equal_to_capacity_is_suitable`, `test_headcount_one_over_capacity_is_not_suitable` (rule and route), `test_exactly_at_capacity_is_requested` |
| TC-SU31 | Booking exactly the operating hours; ending at 23:59 | Suitable | `test_exactly_the_hours_is_suitable`, `test_23_59_closes_at_midnight` |
| TC-SU32 | Hours not recorded, or unreadable | A note, not a reason ("…the booking time was not checked.") | `test_what_could_not_be_checked_is_noted`, `test_hours_not_recorded_are_not_held_against_the_venue`, `test_hours_that_cannot_be_read_are_noted_not_held_against_it`; frontend "shows what could not be checked alongside the verdict" |
| TC-SU33 | Layout in another case or with spaces; a layout name inside another | Matched / not matched | `test_layouts_compare_without_case_or_extra_spaces`, `test_a_layout_is_matched_whole_not_as_part_of_another` |
| TC-SU34 | Venue lists stored as Postgres array literals | Read like plain lists | `TestListedItems`, `test_array_literal_venues_are_assessed_like_any_other` |
| TC-SU35 | Headcount 0 / above 2,147,483,647 | 400, "The headcount must be at least 1." / "That headcount is larger than any venue this system can hold." | `test_a_headcount_that_is_not_a_count_of_people` (parametrised); frontend "refuses a headcount of nobody before sending anything" |

## 5. Recorded results

| Check | Date | Result |
| --- | --- | --- |
| Backend `pytest` on the files above | 2026-10-23 | 229 passed |
| Frontend `vitest` on the files above | 2026-10-23 | 105 passed |

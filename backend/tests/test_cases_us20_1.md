# Test Cases for US20.1: Attendee Registers for an Event

> As an Attendee, I want to register for a confirmed event, so that I have a
> place at it.

## Acceptance Criteria

| # | Criterion | Status |
| --- | --- | --- |
| AC1 | The assigned Coordinator can turn registration on for an event and set a registration capacity (whole number ≥ 1, defaults to expected attendance) | Done |
| AC2 | Attendees see Confirmed events with registration turned on: name, date/time, venue(s) and places left. Internal planning info (bookings, equipment, notes) is never shown to Attendees | Done |
| AC3 | An Attendee registers with name and email (both required). Only one active registration per Attendee per event | Done |
| AC4 | Once registrations reach capacity, registering is blocked with an "Event is full" message. If two Attendees try for the last place at the same time, only one succeeds (enforced in the database) | Done — row lock, trigger and unique index |
| AC5 | The Coordinator and Organiser are notified when the event becomes full (US10.2) | Done |

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

### Team assumptions (not customer-confirmed)
- **Attendees sign in.** The Attendee role is modelled from this story on (it has
  been in `user_role` all along), with one permission, `registrations:create`,
  and lands on Upcoming Events (`/attend`). "One registration per Attendee" counts
  by account. The form's name and email start as the account's own and can be
  changed.
- **When registration can be turned on:** from Approved until the event is over
  (Approved, Planning, Pending Safety Check, Confirmed). Attendees only see it once
  it is Confirmed, so a Coordinator can open it ahead of that. Before approval the
  event may still be turned down; afterwards there is nothing to register for. A
  Cancelled event is read-only, as US4.6 makes every event route.
- **The capacity** starts at the expected attendance. A capacity given wins; once
  one is stored, turning registration off and on again keeps it. It may not go
  below the places already taken.
- **Turning registration off** stops new registrations and hides the event from
  Attendees; existing registrations stay.
- **"Venue(s)"** are the venues of the event's Confirmed bookings. A Confirmed
  event's bookings are all Confirmed (US4.4 requires it).
- **"Becomes full"** means the registration that takes the last place. Exactly one
  registration can, so exactly one notice goes to each of the Coordinator and the
  Organiser. Raising the capacity and filling it again sends a new one. A
  Coordinator who lowers the capacity to the places taken has made it full
  themselves, and nobody else is told.
- **Email** is checked for shape only (something@something.something). It is shown
  to people, never mailed.
- **Only Registered counts as active.** US20.2 (withdrawing) and US4.6 (Event
  Cancelled) add their statuses; the one-per-Attendee index and the capacity both
  count only Registered, so those become history without more changes here.

## Workflow Visualization

```
Assigned Coordinator (Approved … Confirmed)
   PUT /events/{id}/registration {"open": true, "capacity": 50 | omitted → attendance}
        │                              set_event_registration: locks the event,
        │                              capacity ≥ places taken
        ▼
Event Confirmed + registration on ──► GET /attendee/events (Attendee)
                                       name, when, venues, places left, registered?
                                            │
   POST /attendee/events/{id}/registrations {"name", "email"}
        │  404 not open · 400 name/email
        ▼
   register_for_event: lock the event row, then
        ├─ already registered ─► 409 already-registered
        ├─ no places left ─────► 409 event-full "Event is full."
        └─ insert (trigger re-checks under the same lock)
              └─ took the last place? ─► notice "event-full" to Coordinator + Organiser

Two at once for the last place: the second waits on the lock, then counts the
first and is told "Event is full."
```

## Test Files

| Layer | File |
| --- | --- |
| Backend | `backend/tests/test_registration_us20_1.py` |
| Backend (store) | `backend/tests/test_registration_store.py` — the Supabase store's queries and how it reads each answer |
| Backend (real database, opt-in) | `backend/tests/test_registration_db.py` — the functions, trigger and index, and two connections at once |
| Backend (regressions) | `test_users.py` (Attendee now modelled) |
| Frontend | `EventRegistration.test.tsx`, `AttendPage.test.tsx`, `registrationStore.test.ts`, `permissions.test.ts` (US20.1 block), `App.test.tsx` (US20.1 block), `NotificationsPage.test.tsx` (event-full), `EventDetailPage.test.tsx` (the card on the page) |
| Database | `backend/SUPABASE_US20_1_REGISTRATION.sql` |
| Database (SQL Editor, no DB URL needed) | `backend/TEST_US20_1_REGISTRATION.sql` — one block that always rolls back; read the result from the error message |

---

## 1. HAPPY PATH TEST CASES

### TC-RG01: The assigned Coordinator turns registration on with a capacity (AC1)
- **Pre-conditions**: Event Confirmed, assigned to Priya, expected attendance 30
- **Test Steps**: `PUT /events/950/registration` with `{"open": true, "capacity": 50}`
- **Expected Result**: 200, `{"open": true, "capacity": 50, "registered": 0, "placesLeft": 50, "defaultCapacity": 30}`
- **Automated**: `test_the_assigned_coordinator_turns_it_on_with_a_capacity`; frontend "turns registration on with the capacity shown", "sends a capacity the Coordinator typed"

### TC-RG02: The capacity defaults to the expected attendance (AC1)
- **Test Steps**: `PUT` with `{"open": true}` and no capacity; on the page, the box starts at the attendance
- **Expected Result**: capacity 120 for an event expecting 120
- **Automated**: `test_the_capacity_defaults_to_the_expected_attendance`, `test_an_empty_box_is_no_capacity_so_the_attendance_is_used`; frontend "offers the assigned Coordinator the switch, with the capacity starting at the attendance", "sends an emptied box as no capacity, for the server to default"

### TC-RG03: Registration can be opened before the event is Confirmed (AC1)
- **Expected Result**: 200 for a Planning event; the card says Attendees will see it once it is Confirmed
- **Automated**: `test_it_can_be_opened_before_the_event_is_confirmed`; frontend "says Attendees see it only once it is Confirmed"

### TC-RG04: Attendees see the event, and only what they need (AC2)
- **Pre-conditions**: Confirmed, registration on (30 places), a Confirmed booking of Great Hall
- **Test Steps**: `GET /attendee/events` as an Attendee
- **Expected Result**: `[{"id", "title", "startsAt", "endsAt", "venues", "placesLeft", "registered"}]` and no other field; nothing from the description, purpose, bookings, equipment, history, Organiser or Coordinator
- **Automated**: `test_a_confirmed_event_taking_registrations_is_listed`, `test_nothing_of_the_planning_is_shown`; frontend "shows each open event with when, where and the places left"

### TC-RG05: The venues are the Confirmed bookings, once each (AC2)
- **Expected Result**: Confirmed Great Hall (twice) and Seminar Room 4 → `["Great Hall", "Seminar Room 4"]`; Cancelled and Rejected bookings and another event's bookings are not shown; none → "Venue to be announced"
- **Automated**: `test_the_venues_are_its_confirmed_bookings_once_each`; frontend "says the venue is to be announced when none is confirmed"

### TC-RG06: An Attendee registers with a name and an email (AC3)
- **Test Steps**: Register on Upcoming Events; the form starts with the account's name and email
- **Expected Result**: 201 `{"status": "Registered", ...}`, stored against the Attendee's account; the page says "You are registered for Open House." and the card shows "You are registered for this event."
- **Automated**: `test_an_attendee_registers_with_a_name_and_an_email`, `test_what_was_typed_is_trimmed`; frontend "starts the form with the account’s own name and email", "registers, says so, and reads the list again"

### TC-RG07: Places count down (AC2, AC4)
- **Expected Result**: 2 → 1 → 0 places left; a full event is still listed, with no Register button
- **Automated**: `test_places_left_count_down_and_a_full_event_stays_listed`; frontend "offers no Register button on a full event", "says one place in the singular"

### TC-RG08: The Coordinator and the Organiser are told when it fills (AC5)
- **Pre-conditions**: 2 places
- **Expected Result**: nothing after the first registration; after the second, one `event-full` notice each to Priya and Dylan: `"Open House" is full: all 2 places are taken.`; both see it on their notifications page, labelled "Event full", linking to the event
- **Automated**: `test_both_are_told_once_when_the_last_place_is_taken`, `test_both_read_it_on_their_notifications_page`; frontend "labels the event-full notice and links to the event (US20.1)"

### TC-RG09: The whole journey
- **Expected Result**: opened in Planning → not listed → Confirmed → listed → registered → full, with two notices
- **Automated**: `test_opened_in_planning_listed_once_confirmed_then_filled`

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-RG10: Two at once for the last place: only one succeeds (AC4)
- **Pre-conditions**: 1 place, two Attendees
- **Expected Result**: in the database, the second registration waits on the event's lock while the first is uncommitted, then answers `full`; two at the same moment give exactly one `registered` and one `full`. Without the lock both would get the place (checked by removing it: both tests fail)
- **Automated**: `TestTwoAtOnce` (`test_registration_db.py`); the in-memory store holds the same contract: `test_two_at_once_for_the_last_place_only_one_gets_it`

### TC-RG11: The database refuses whatever writes the row (AC3, AC4)
- **Expected Result**: a direct `INSERT` past the capacity, or for an event with registration off, is refused by the trigger; a second active row for one Attendee by the unique index
- **Automated**: `test_the_trigger_refuses_a_direct_insert_beyond_capacity`, `test_the_trigger_refuses_a_direct_insert_when_registration_is_off`, `test_the_index_refuses_a_second_active_row_for_one_attendee`; `TEST_US20_1_REGISTRATION.sql`

### TC-RG12: An Attendee reaches nothing internal (AC2)
- **Expected Result**: `/events`, `/events/{id}`, its bookings, equipment and registration settings, `/venues` and `/notifications` all answer 403; the page's guard keeps Attendees out of the internal pages too
- **Automated**: `test_an_attendee_reaches_none_of_the_internal_routes`; frontend "keeps an Attendee out of the internal events list", "keeps Attendees out of every internal page"

### TC-RG13: A notice that fails never undoes the registration (AC5)
- **Automated**: `test_a_notice_that_cannot_be_written_never_undoes_the_registration`, `test_a_failed_read_for_the_notice_does_not_undo_it_either`

### TC-RG14: The Attendee role
- **Expected Result**: an Attendee signs in, lands on `/attend` and holds only `registrations:create`; only the Coordinator holds `registration:manage`; the header offers Upcoming Events and not Events
- **Automated**: `test_an_attendee_signs_in_and_lands_on_the_open_events`, `test_each_permission_belongs_to_one_role`, `test_attendee_became_a_modelled_role_with_us20_1`; frontend "routes an Attendee to the events open for registration on sign-in"

### TC-RG15: Everyone else who can open the event sees where it stands (AC1)
- **Expected Result**: the Organiser, the Coordinator and the Lead read the settings; the Organiser sees "Registration is on: 3 of 50 places taken." with nothing to change; a full event says so
- **Automated**: `test_anyone_who_can_open_the_event_reads_the_settings`; frontend "shows the Organiser where it stands, with nothing to change", "says when the event is full"

### TC-RG16: A refusal is shown where the user is
- **Expected Result**: the Coordinator's form keeps what was typed and shows the server's reason; the Attendee's form shows "Event is full." when the last place went first, and the list is read again
- **Automated**: frontend "shows the server’s refusal and keeps what was typed", "says the event is full when the last place went first, and shows the places now", "explains an unexpected failure to register", "explains an unexpected failure to save"

---

## 3. NEGATIVE TEST CASES

| ID | Scenario | Expected | Automated |
| --- | --- | --- | --- |
| TC-RG20 | Organiser, Lead, Venue Staff, Safety Officer or Attendee changes the settings | 403, "The Event Organiser role cannot open or close registration for events. That is available to: Event Coordinator." | `test_no_other_role_may_change_it`, `test_the_denial_names_who_may` |
| TC-RG21 | A Coordinator the event is not assigned to | 404 on read and write; no switch on the page | `test_a_coordinator_not_assigned_to_the_event_gets_not_found`; frontend "offers no switch to a Coordinator the event is not assigned to" |
| TC-RG22 | Submitted or Under Review | 409 `not-approved`, "Approve this event before opening registration."; the page says it opens after approval | `test_not_before_approval` (both classes); frontend "tells the Coordinator it opens after approval, rather than offering it" |
| TC-RG23 | Completed or Rejected; Cancelled | 409 `event-closed`; 409 `event-cancelled` | `test_not_once_it_is_over`, `test_a_cancelled_event_is_read_only`; frontend "offers nothing to change on a closed event" |
| TC-RG24 | Capacity 0, -1, 1.5, "abc", true, "1e3" | 400 `invalid_registration`, "Give the capacity as a whole number of places, at least 1." | `test_anything_but_a_whole_number_of_at_least_one_is_refused`; frontend "refuses a capacity of nobody before sending anything" |
| TC-RG25 | No capacity and no expected attendance | 400, "Give a capacity: this event has no expected attendance to start from." | `test_with_no_attendance_a_capacity_must_be_given` |
| TC-RG26 | A capacity below the places taken | 409 `below-registered`, "2 people have already registered, so the capacity cannot be less than 2." | `test_it_cannot_go_below_the_places_taken` |
| TC-RG27 | An event not Confirmed, registration off, never opened, unknown, or a non-numeric id | Not listed; 404 `event_not_open`, "That event is not open for registration." | `test_anything_else_is_not_listed`, `test_a_confirmed_event_never_opened_is_not_listed`, `test_an_unknown_event_is_not_open` (both classes) |
| TC-RG28 | Blank or missing name | 400, "Give your name."; nothing stored; checked before the email | `test_a_name_is_required`, `test_missing_fields_are_the_same_sentences`, `test_the_name_is_checked_before_the_email`; frontend "asks for a name before sending anything" |
| TC-RG29 | Blank email; "casey", "casey@", "@example.com", "casey@example", "casey tan@example.com" | 400, "Give your email address." / "Give a valid email address, such as name@example.com." | `test_an_email_is_required`, `test_an_email_that_cannot_be_one_is_refused`; frontend "refuses an email that cannot be one before sending anything" |
| TC-RG30 | Registering twice | 409 `already-registered`, "You are already registered for this event."; one row; the page offers no second place | `test_registering_twice_is_refused_with_the_reason`; frontend "offers no second place once registered" |
| TC-RG31 | Registering for a full event | 409 `event-full`, "Event is full."; nothing stored; no second notice | `test_the_last_place_is_taken_and_the_next_is_refused`, `test_a_refused_registration_says_nothing_new` |
| TC-RG32 | Any role but Attendee on the Attendee routes | 403 | `test_only_attendees_use_the_attendee_routes` |
| TC-RG33 | Registration turned off meanwhile | 404; existing registrations kept | `test_turning_registration_off_stops_new_ones_and_keeps_the_old`, `test_closing_between_the_check_and_the_write_is_not_open` |
| TC-RG34 | Signed out | 401 | `test_signed_out_is_asked_to_sign_in` (both classes) |
| TC-RG35 | In the database: a non-Attendee account, a blank name or email, a missing event | `not-attendee`, `invalid`, `closed` | `test_only_an_attendee_registers`, `test_a_blank_name_or_email_is_invalid`, `test_a_missing_event_is_closed` |

## 4. BOUNDARY TEST CASES

| ID | Boundary | Expected | Automated |
| --- | --- | --- | --- |
| TC-RG40 | Capacity 1 / 2,147,483,647 / 2,147,483,648 | Taken / taken / 400 "That capacity is larger than this system can hold." | `test_whole_numbers_are_taken_however_they_are_sent`, `test_one_more_than_the_column_holds_is_refused`; frontend `parseCapacity` tests |
| TC-RG41 | Capacity "12" or 12.0 | Read as 12 | `test_whole_numbers_are_taken_however_they_are_sent` |
| TC-RG42 | Capacity equal to the places taken | Allowed; 0 places left | `test_exactly_the_places_taken_is_allowed_and_leaves_none` |
| TC-RG43 | One place | Its registration takes it and says so: `"Open House" is full: its one place is taken.` | `test_one_place_reads_in_the_singular` |
| TC-RG44 | The last place, then one more | 201, then 409 `event-full` | `test_the_last_place_is_taken_and_the_next_is_refused` |
| TC-RG45 | Already registered on a full event | `already-registered`, not `event-full` | `test_already_registered_is_said_before_full` (API and database) |
| TC-RG46 | Raising the capacity of a full event | Registrations taken again; filling it again tells them again | `test_raising_the_capacity_takes_registrations_again`, `test_filling_again_after_more_places_tells_them_again` |
| TC-RG47 | Turning off and on again | The stored capacity is kept, not reset to the attendance | `test_turning_it_off_keeps_the_capacity_for_next_time`, `test_the_coordinator_saves_and_a_null_capacity_keeps_the_stored_one` |
| TC-RG48 | Name or email of 255 / 256 characters | Taken / refused | frontend "takes 255 characters and refuses 256" |
| TC-RG49 | No Coordinator on the event when it fills | The Organiser is still told | `test_with_no_coordinator_the_organiser_is_still_told` |
| TC-RG50 | Several open events | Soonest first | `test_soonest_first` |

## 5. The database

`SUPABASE_US20_1_REGISTRATION.sql` adds `events.registration_open` and
`registration_capacity` (with checks: capacity ≥ 1, and on means a capacity), the
`registrations` table (`registration_status` holds only Registered), a partial
unique index for one active registration per Attendee, the
`enforce_registration_capacity` trigger, the `register_for_event` and
`set_event_registration` functions (both lock the event row first; both answer
with an outcome rather than an error), and the `event-full` notice kind. It is
safe to run twice.

## 6. Recorded results

| Check | Date | Result |
| --- | --- | --- |
| Migration applied twice to a local Postgres built from every earlier `SUPABASE_*.sql` script | 2026-10-23 | Applied cleanly both times |
| `TEST_US20_1_REGISTRATION.sql` against that local database | 2026-10-23 | **US20.1 PASSED - all 22 checks**; rolled back |
| `test_registration_db.py` against that local database | 2026-10-23 | 26 passed, the two at-once tests included. With the row lock removed, both at-once tests fail (both Attendees got the last place) |
| Backend `ruff check`, `compileall`, `pytest` | 2026-10-23 | Clean; 1871 passed, 2 skipped (the two opt-in database files) |
| Frontend `oxlint`, `tsc -b`, `vitest` | 2026-10-23 | Clean; 995 passed |
| Migration applied to the live Supabase project | — | **Not yet**: run `SUPABASE_US20_1_REGISTRATION.sql`, then `TEST_US20_1_REGISTRATION.sql`, and record the result here |
| Attendee accounts in the live project | — | **Not yet**: `python seed_new_users.py --attendees-only` |

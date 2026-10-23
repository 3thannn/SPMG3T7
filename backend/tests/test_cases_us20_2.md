# Test Cases for US20.2: Attendee Views Registration and Withdraws

> As an Attendee, I want to see my registrations and withdraw if I can't go, so
> that I always have the latest event details and my place can go to someone
> else.

## Acceptance Criteria

| # | Criterion | Status |
| --- | --- | --- |
| AC1 | An Attendee sees their registrations with status (Registered or Withdrawn) and the event's current date, time and venue | Done — My Registrations |
| AC2 | An Attendee can withdraw before the event starts. Available places left goes up by 1 | Done |
| AC3 | A withdrawn Attendee can register again if places are still available | Done |

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

### Team assumptions (not customer-confirmed)
- **"Current" details are read when the page loads**, not copied at registration:
  the event's title, date, time and the venues of its Confirmed bookings, so a
  moved event shows where it moved to.
- **One entry per event.** Someone who withdrew and registered again has two rows
  for the event; the list shows the newer, which is where they stand. The older
  stays in the table as history.
- **"Before the event starts"** means before its start date and time, in Singapore
  time like every event time. At the start time itself it is too late.
- **Only while the event is Confirmed.** A registration on an event that has been
  completed or is no longer going ahead cannot be withdrawn (US4.6 will mark those
  "Event Cancelled").
- **Withdrawing still works with registration turned off**: it only gives a place
  back. Registering again needs registration on and a place left, as any
  registration does (US20.1).
- **Registering again is a new registration** through US20.1's route, with the same
  rules and the same "Event is full" notice when it takes the last place. The page
  re-uses the name and email from before.
- **Withdrawing asks first**, because the place may be gone by the time the Attendee
  changes their mind.

## Workflow Visualization

```
My Registrations (GET /attendee/registrations)
   one card per event: status, current date/time/venues, registered/withdrawn time
        │
   Registered, event Confirmed, before its start ── "Withdraw…" ── confirm
        │
   POST /attendee/registrations/{id}/withdraw
        ├─ not theirs / missing ─► 404
        ├─ already withdrawn ────► 409 already-withdrawn
        ├─ started ──────────────► 409 event-started
        ├─ not Confirmed ────────► 409 event-closed
        └─ withdraw_registration: lock the event, then the row
              → Withdrawn + withdrawn_at; the place is free (places left + 1)
        │
   Withdrawn, registration on, a place left ── "Register again"
        └─ POST /attendee/events/{id}/registrations (US20.1) → a new Registered row
```

## Test Files

| Layer | File |
| --- | --- |
| Backend | `backend/tests/test_registration_us20_2.py` |
| Backend (store) | `backend/tests/test_registration_store.py` — `TestAnAttendeesRegistrations`, `TestWithdrawing` |
| Backend (real database, opt-in) | `backend/tests/test_registration_db.py` — `TestWithdrawingInTheDatabase` |
| Frontend | `MyRegistrationsPage.test.tsx`, `registrationStore.test.ts` (US20.2 block), `permissions.test.ts`, `App.test.tsx`, `AttendPage.test.tsx` (the link to My Registrations) |
| Database | `backend/SUPABASE_US20_2_WITHDRAW.sql` |
| Database (SQL Editor, no DB URL needed) | `backend/TEST_US20_2_WITHDRAW.sql` — one block that always rolls back |

---

## 1. HAPPY PATH TEST CASES

### TC-WD01: An Attendee sees their registration (AC1)
- **Pre-conditions**: Casey registered for Open House (Confirmed, Great Hall confirmed, 30 places)
- **Test Steps**: `GET /attendee/registrations`; open My Registrations
- **Expected Result**: one entry: title, start and end, `["Great Hall"]`, status Registered, the name and email registered with, when (in Singapore time), `canWithdraw: true`, `placesLeft: 29`
- **Automated**: `test_an_attendee_sees_their_registration`; frontend "shows each registration with its status and the event as it is now"

### TC-WD02: The event's details are the current ones (AC1)
- **Test Steps**: after registering, the event is renamed and moved, and a different venue is confirmed
- **Expected Result**: the list shows the new title, start and venue
- **Automated**: `test_the_event_details_are_the_current_ones`

### TC-WD03: A withdrawn registration shows as Withdrawn (AC1)
- **Expected Result**: status Withdrawn, with when it was withdrawn; no Withdraw button
- **Automated**: `test_a_withdrawn_registration_is_listed_as_withdrawn`; frontend "shows a withdrawn registration as Withdrawn, with when"

### TC-WD04: An Attendee withdraws before the event starts (AC2)
- **Test Steps**: Withdraw… → Confirm withdrawal (`POST /attendee/registrations/{id}/withdraw`)
- **Expected Result**: 200; status Withdrawn, `withdrawnAt` set, `canWithdraw: false`, `canRegisterAgain: true`; the page says "You have withdrawn from Open House. Your place has gone back to the event."; the row is kept as history
- **Automated**: `test_an_attendee_withdraws_before_the_event_starts`, `test_the_registration_is_kept_as_history`; frontend "asks before withdrawing, then withdraws and reads the list again"

### TC-WD05: The places left go up by one (AC2)
- **Pre-conditions**: 2 places, both taken
- **Expected Result**: after one withdrawal, Upcoming Events shows 1 place left and the Coordinator's card 1 registered, 1 place left; the freed place can be taken by someone else
- **Automated**: `test_the_places_left_go_up_by_one`, `test_the_freed_place_can_be_taken_by_someone_else`

### TC-WD06: A withdrawn Attendee registers again (AC3)
- **Test Steps**: Register again
- **Expected Result**: 201; a new Registered row beside the Withdrawn one; the event counts one place taken; the list shows one entry, Registered; the page says "You are registered again for Open House."
- **Automated**: `test_a_withdrawn_attendee_registers_again`, `test_one_entry_per_event_where_they_stand_now`; frontend "registers again with the same name and email, and says so"

### TC-WD07: The whole journey
- **Automated**: `test_register_withdraw_and_register_again`

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-WD10: The database decides, under the event's lock
- **Expected Result**: `withdraw_registration` locks the event before the registration, the order registering takes them in, so a withdrawal and a registration for the same event queue rather than deadlock; a Withdrawn row always records when; bringing a Withdrawn row back to Registered directly is still held to the capacity
- **Automated**: `TestWithdrawingInTheDatabase`; `TEST_US20_2_WITHDRAW.sql`

### TC-WD11: The page asks first, and backs out cleanly
- **Expected Result**: Withdraw… shows a warning and Confirm withdrawal / Keep my place; Keep my place withdraws nothing
- **Automated**: frontend "asks before withdrawing, then withdraws and reads the list again", "keeps the place when the Attendee changes their mind"

### TC-WD12: Only the Attendee's own, and nothing of the planning
- **Expected Result**: another Attendee's registrations are not listed; no description, notes, Organiser or Coordinator in the response
- **Automated**: `test_only_your_own`, `test_nothing_of_the_planning_is_shown`

### TC-WD13: Upcoming Events points to where withdrawing is done
- **Automated**: frontend "offers no second place once registered" (the My Registrations link)

### TC-WD14: Registering again takes the last place and says so
- **Expected Result**: the Coordinator and the Organiser are told it is full again (US20.1 AC5)
- **Automated**: `test_taking_the_last_place_again_tells_them_it_is_full`

---

## 3. NEGATIVE TEST CASES

| ID | Scenario | Expected | Automated |
| --- | --- | --- | --- |
| TC-WD20 | Withdrawing after the event has started | 409 `event-started`, "This event has already started, so you can no longer withdraw."; still Registered; the page says withdrawing has closed | `test_once_the_event_has_started_it_is_too_late`; frontend "shows the server’s refusal on the registration it was about", "offers no withdrawal once it has closed" |
| TC-WD21 | Withdrawing twice | 409 `already-withdrawn`, "You have already withdrawn from this event." | `test_withdrawing_twice_is_refused_with_the_reason` |
| TC-WD22 | The event Completed or Cancelled | 409 `event-closed` | `test_an_event_no_longer_going_ahead_is_refused` |
| TC-WD23 | Another Attendee's registration; an unknown or non-numeric id | 404 `registration_not_found`, "That registration no longer exists."; unchanged | `test_someone_elses_registration_is_not_found`, `test_an_unknown_registration_is_not_found` |
| TC-WD24 | Registering again when the places have gone | 409 "Event is full."; the entry stays Withdrawn with no Register again | `test_not_once_the_places_have_gone`; frontend "says the event is full when the place went to someone else first" |
| TC-WD25 | Registering again once registration is turned off | 404; the page says the event is no longer taking registrations | `test_not_once_registration_is_turned_off`; frontend "says why there is no way back when registration has closed" |
| TC-WD26 | Any role but Attendee | 403 on the list and on withdrawing | `test_only_attendees_have_registrations_to_see`; frontend `permissions.test.ts` "lets only Attendees open their registrations (US20.2)" |
| TC-WD27 | Signed out | 401 | `test_signed_out_is_asked_to_sign_in` |

## 4. BOUNDARY TEST CASES

| ID | Boundary | Expected | Automated |
| --- | --- | --- | --- |
| TC-WD30 | One minute before the start / at the start | Withdrawn / 409 `event-started` | `test_up_to_the_minute_before_it_starts`, `TestTheRule` |
| TC-WD31 | Withdrawing from a full event | It is no longer full; the next Attendee gets the place | `test_the_freed_place_can_be_taken_by_someone_else` |
| TC-WD32 | Registration turned off | Withdrawing still allowed; no Register again | `test_registration_turned_off_still_lets_you_withdraw` |
| TC-WD33 | No registrations | An empty list; the page points to Upcoming Events | `test_none_is_an_empty_list`; frontend "says when there are none, and where to find events" |
| TC-WD34 | Withdrawn and re-registered | One entry, the newer | `test_one_entry_per_event_where_they_stand_now` |
| TC-WD35 | An event with no start recorded | Not started | `test_an_event_with_no_start_recorded_has_not_started` |

## 5. The database

`SUPABASE_US20_2_WITHDRAW.sql` adds `Withdrawn` to `registration_status`, the
`withdrawn_at` column with a check that a Withdrawn row always has one, and the
`withdraw_registration` function. The new value is only compared as text in the
script, because Postgres refuses an enum value added in the same transaction
that uses it and the SQL Editor runs a script as one. Registering again needs
nothing new: US20.1 counts only Registered rows.

## 6. Recorded results

| Check | Date | Result |
| --- | --- | --- |
| Migration applied twice, as one script, to a local Postgres built from every earlier `SUPABASE_*.sql` script | 2026-10-23 | Applied cleanly both times |
| `TEST_US20_2_WITHDRAW.sql` against that local database | 2026-10-23 | **US20.2 PASSED - all 11 checks**; rolled back. `TEST_US20_1_REGISTRATION.sql` still passes all 22 |
| `test_registration_db.py` against that local database | 2026-10-23 | 35 passed (US20.1 and US20.2) |
| Backend `ruff check`, `compileall`, `pytest` | 2026-10-23 | Clean; 1926 passed, 2 skipped (the two opt-in database files) |
| Frontend `oxlint`, `tsc -b`, `vitest` | 2026-10-23 | Clean; 1014 passed |
| Migration applied to the live Supabase project | — | **Not yet**: after US20.1's, run `SUPABASE_US20_2_WITHDRAW.sql`, then `TEST_US20_2_WITHDRAW.sql`, and record the result here |

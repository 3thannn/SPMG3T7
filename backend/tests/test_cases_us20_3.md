# Test Cases for US20.3: Organiser and Coordinator View Registrations

> As an Event Organiser or Event Coordinator, I want to see who has registered for
> my event, so that I can plan for the actual numbers.

## Acceptance Criteria

| # | Criterion | Status |
| --- | --- | --- |
| AC1 | The owning Organiser and the assigned Coordinator can see the registration list: name, email, registration time, status, and registered count vs capacity | Done — on the event's Registration card |
| AC2 | Other Organisers and non-assigned Coordinators are blocked (US3.1 / US8.6 rules). Attendees can't see other Attendees' registrations | Done |

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

### Team assumptions (not customer-confirmed)
- **Only the two named people.** The list holds names and emails, so it gets its own
  permission, `registrations:read`, held by the Organiser and Coordinator roles; the
  event check then admits only the Organiser who owns it and the Coordinator assigned
  to it. The Coordinator Lead can read every event (US8.6) but is not named in the
  story, so is refused (403), as are Venue Staff, the Safety Officer, Tech Support
  and Attendees.
- **A non-owner or non-assigned Coordinator gets 404**, not 403: the same answer US3.1
  and US8.6 give for the event itself, so the answer does not confirm the event
  exists.
- **One entry per person**, their newest registration. Someone who withdrew and
  registered again is listed once, as Registered. A withdrawn registration stays on
  the list, marked Withdrawn with when, and does not count.
- **"Registration time"** is when the shown registration was made, in Singapore time;
  the list is in that order.
- **The count** is places taken (Registered only) against the capacity, with the
  places left; before a capacity is set it reads "N registered".
- **No database change.** The list reads what US20.1 and US20.2 store.

## Workflow Visualization

```
GET /events/{id}/registrations
   ├─ role without registrations:read (Lead, Venue Staff, Safety, Tech, Attendee) ─► 403
   ├─ not the owner / not the assigned Coordinator / a Coordinator on a Draft ────► 404
   └─ owning Organiser or assigned Coordinator ─► {open, capacity, registered, placesLeft,
                                                   registrations: [{name, email, status,
                                                   registeredAt, withdrawnAt}]}
        │
Event page → Registration card → "Who has registered"
   "1 of 50 registered" · table: Name | Email | Registered | Status
```

## Test Files

| Layer | File |
| --- | --- |
| Backend | `backend/tests/test_registration_us20_3.py` |
| Backend (store) | `backend/tests/test_registration_store.py` — `TestAnEventsRegistrations` |
| Backend (regressions) | `test_access_enforcement.py` (what Organisers and Coordinators share) |
| Frontend | `EventRegistration.test.tsx` (US20.3 block), `registrationStore.test.ts` (US20.3 block) |

---

## 1. HAPPY PATH TEST CASES

### TC-RL01: The owning Organiser and the assigned Coordinator see the list (AC1)
- **Pre-conditions**: Casey registered for Open House
- **Test Steps**: `GET /events/950/registrations` as Dylan (owner) and as Priya (assigned)
- **Expected Result**: 200 for both, listing Casey Tan
- **Automated**: `test_the_owning_organiser_and_the_assigned_coordinator_see_it`; frontend "shows the assigned Coordinator who registered, with the count against the capacity", "shows the owning Organiser the same list"

### TC-RL02: Name, email, registration time, status, and the count (AC1)
- **Pre-conditions**: 50 places; Casey and Morgan registered
- **Expected Result**: `{"open": true, "capacity": 50, "registered": 2, "placesLeft": 48}` and both people with name, email, Registered and when; on the card, "1 of 50 registered" and a table of Name, Email, Registered (Singapore time) and Status
- **Automated**: `test_each_person_with_the_count_against_the_capacity`, `test_only_these_fields_for_each_person`; frontend "shows the assigned Coordinator who registered, with the count against the capacity"

### TC-RL03: A withdrawn registration is listed and not counted (AC1)
- **Expected Result**: status Withdrawn with when; registered 0, places left back to 50; the card shows "Withdrawn <time>"
- **Automated**: `test_a_withdrawn_registration_is_listed_and_not_counted`; frontend "shows the assigned Coordinator who registered, with the count against the capacity" (Morgan's row)

### TC-RL04: Someone who registered again is listed once (AC1)
- **Expected Result**: one entry, Registered, the newer registration; registered 1
- **Automated**: `test_someone_who_registered_again_is_listed_once`

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-RL10: Only these fields, and only this event's people
- **Expected Result**: each entry is id, name, email, status, registeredAt, withdrawnAt — no account id; registrations for other events are not listed
- **Automated**: `test_only_these_fields_for_each_person`, `test_registrations_for_other_events_are_not_listed`

### TC-RL11: The page asks only when the viewer may see it
- **Expected Result**: the Lead, another Organiser and a Coordinator not assigned see the card's summary but no list, and the page never requests it
- **Automated**: frontend "does not ask for the list for anyone else"

### TC-RL12: The count follows the Coordinator's changes
- **Expected Result**: after saving a capacity the list is read again: "0 of 30 registered"
- **Automated**: frontend "reads the list again after the Coordinator saves"

### TC-RL13: The list survives registration being turned off
- **Expected Result**: open false, the people still listed and counted
- **Automated**: `test_turning_registration_off_keeps_the_list`

---

## 3. NEGATIVE TEST CASES

| ID | Scenario | Expected | Automated |
| --- | --- | --- | --- |
| TC-RL20 | Another Organiser | 404; no names in the answer | `test_another_organiser_is_told_it_does_not_exist` |
| TC-RL21 | A Coordinator not assigned to the event | 404; no names in the answer | `test_a_coordinator_not_assigned_is_told_it_does_not_exist` |
| TC-RL22 | Coordinator Lead, Venue Staff, Safety Officer, Tech Support, Attendee | 403, "The Event Coordinator Lead role cannot see who has registered for events. That is available to: Event Organiser, Event Coordinator." | `test_no_other_role_sees_it`, `test_the_denial_names_who_may` |
| TC-RL23 | An Attendee asks for an event's list | 403; no other Attendee's name in the answer | `test_an_attendee_cannot_open_an_events_list` |
| TC-RL24 | An Attendee's own list, the open events, registering | Only their own registration anywhere; nobody else's name or email | `test_their_own_list_has_only_their_registrations`, `test_the_open_events_carry_no_one_elses_details`, `test_registering_answers_with_your_own_registration_only` |
| TC-RL25 | An Attendee withdraws someone else's registration | 404, nothing about them in the answer | `test_someone_elses_registration_cannot_be_withdrawn` |
| TC-RL26 | A Coordinator on a Draft; unknown or non-numeric event; signed out | 404 / 404 / 401 | `test_a_coordinator_cannot_see_a_draft`, `test_an_unknown_event_is_not_found`, `test_signed_out_is_asked_to_sign_in` |
| TC-RL27 | The list will not load | The card says so | frontend "reports a list that will not load" |

## 4. BOUNDARY TEST CASES

| ID | Boundary | Expected | Automated |
| --- | --- | --- | --- |
| TC-RL30 | Nobody registered, no capacity set | `{"open": false, "capacity": null, "registered": 0, "placesLeft": null, "registrations": []}`; "0 registered", "Nobody has registered yet." | `test_an_event_never_opened_has_no_capacity_and_nobody`; frontend "says when nobody has registered, before a capacity is set" |
| TC-RL31 | Full | registered = capacity, 0 places left | `test_a_full_event_has_no_places_left` |
| TC-RL32 | The Organiser's own Draft | 200, nobody on it | `test_the_organiser_sees_their_own_draft_with_nobody_on_it` |
| TC-RL33 | Order | By when each registered | `test_in_the_order_they_registered` |

## 5. Recorded results

| Check | Date | Result |
| --- | --- | --- |
| Backend `ruff check`, `compileall`, `pytest` | 2026-10-23 | Clean; 1956 passed, 2 skipped (the two opt-in database files) |
| Without the per-event check (`_readable`) | 2026-10-23 | 4 tests fail: another Organiser, a non-assigned Coordinator, a Draft and an unknown event all got an answer. Restored |
| Frontend `oxlint`, `tsc -b`, `vitest`, `build` | 2026-10-23 | Clean; 1021 passed |
| Live Supabase | — | Nothing to apply: no database change |

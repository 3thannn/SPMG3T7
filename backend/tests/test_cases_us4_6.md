# Test Cases for US4.6: Cancel an Event

> As an Event Organiser or Event Coordinator, I want to cancel an event and have
> its bookings released, so that cancelled events don't keep holding venues and
> equipment.

## Acceptance Criteria

| # | Criterion | Status |
| --- | --- | --- |
| AC1 | The owning Organiser or the assigned Coordinator can cancel any event that isn't Completed, Cancelled or Rejected. Reason required | Done |
| AC2 | Status → Cancelled, logged with who/when. The cancelled event becomes read-only | Done |
| AC3 | All its active venue bookings and holds → Cancelled, and all equipment reservations are released, so the slots and quantities free up | Done |
| AC4 | Registrations are marked Event Cancelled | Done — once US20.1 brought registrations; see "Finishing AC4 and AC5" |
| AC5 | The Coordinator, Organiser, affected Venue Staff, Tech Support and registered Attendees are notified | Done |
| — | Not one of the 20 Release 1 core features; first story to drop if Sprint 4 runs short | — |

## Finishing AC4 and AC5

AC4 and the Attendee half of AC5 waited for the registration epic, because there
were no registrations or Attendees to build them on. US20.1–20.3 brought both, and
they were finished as this document planned:

1. Registrations gained the status `Event Cancelled`.
2. `cancel_event` marks the event's Registered registrations Event Cancelled in the
   same transaction, after the equipment update, closes registration, and returns
   their ids as `registrations` beside `bookings` and `equipment`
   (`SUPABASE_US4_6_CANCEL_REGISTRATIONS.sql`, a new script because the first one
   is already applied to the live project).
3. `InMemoryEvents.cancel_event` mirrors it (`InMemoryRegistrations.cancel_for_event`).
4. `notify_event_cancelled` tells each Attendee whose registration it ended.
   Attendees gained `notifications:read`.
5. The tests are `TestRegistrations` in `tests/test_cancel_event_us4_6.py`.

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

### Team assumptions (not customer-confirmed)
- **Who may cancel which events.** The Organiser who owns the event, at any status
  that is not closed, including their own Draft. The Coordinator it is assigned to,
  once it is submitted (a Coordinator cannot see a Draft). Nobody else, the
  Coordinator Lead included.
- **"Active" bookings and holds** are the ones that still hold their venue:
  Requested, Confirmed, and Held until its expiry (`HOLDS_VENUE`). Cancelled,
  Rejected and expired holds already free their slot, so they keep their own
  status as history. A Confirmed booking that is cancelled keeps the Venue Staff
  decision that confirmed it.
- **"Equipment reservations are released"**: every equipment line not already
  Removed becomes Removed, whatever its status, so it leaves Tech Support's queue.
  Reserved lines (US19.3, not built yet) will be released the same way.
- **Notifications are in-app**, like every other notice. The person who cancels is
  not sent a notice about their own action; they see it on the page.
- **"Affected Venue Staff"**: venues have no assigned staff member, so every Venue
  Staff user is told, and only when the event had bookings to release. Tech Support
  are told only when equipment was released. Venue Staff gained
  `notifications:read` for this.
- **Registrations**: only Registered ones become Event Cancelled; a Withdrawn one
  (US20.2) is history and keeps its status. Registration also closes
  (`registration_open` = false, the capacity kept), and an Event Cancelled
  registration answers `event-closed` to a withdrawal, not "already withdrawn".
- **Attendees are told without the reason.** It is written for the people
  planning the event, and US20.1 keeps internal planning from Attendees. Their
  notice is `"Open House" has been cancelled, so your registration for it is
  cancelled too.` and links to My Registrations, since they cannot open events.
  Only Attendees whose registration was ended are told, each once.
- **Read-only**: every route that changes an event, its bookings, holds or
  equipment refuses a Cancelled event. An Organiser's change request still waiting
  when the event is cancelled stays on record unanswered; nobody can answer it, and
  the pages stop showing it as waiting.

## Workflow Visualization

```
Draft ─┐ (Organiser only)
Submitted, Under Review, Approved, Planning,     "Cancel this event…"
Pending Safety Check, Confirmed ──────────────►  reason required
                                                      │
       one transaction (cancel_event RPC) ◄───────────┘
       ├─ event → Cancelled, history entry: who, when, reason
       ├─ Requested / Confirmed / live Held bookings → Cancelled (reason, who, when)
       ├─ equipment lines → Removed (history: who)
       └─ Registered registrations → Event Cancelled; registration closes
                                                      │
       afterwards, best effort ◄──────────────────────┘
       ├─ US15.2 conflict flags at the freed venues re-checked
       └─ notices: Organiser / Coordinator (not the canceller),
                   Venue Staff (if bookings released), Tech Support (if equipment released),
                   each Attendee whose registration was ended (without the reason)

Completed, Cancelled, Rejected ──► 409, nothing changes
```

## Test Files

| Layer | File |
| --- | --- |
| Backend | `backend/tests/test_cancel_event_us4_6.py` |
| Backend (regressions) | `test_event_decisions.py` (allowlist), `test_safety_check_us4_4.py` (Pending Safety Check exits), `test_access_enforcement.py`, `test_notifications.py`, `test_venue_booking_cancellation.py` |
| Frontend | `CancelEventPanel.test.tsx`, `EventDetailPage.test.tsx` (US4.6 block), `NotificationsPage.test.tsx` (US4.6 block), `status.test.ts`, `eventsStore.test.ts`, `permissions.test.ts`, `TopNav.test.tsx` |
| Backend (registrations) | `test_cancel_event_us4_6.py` (`TestRegistrations`), `test_registration_us20_2.py` (`test_one_the_events_cancellation_ended_is_closed_not_withdrawn`), `test_registration_db.py` (`TestCancellingTheEvent`, opt-in) |
| Frontend (registrations) | `MyRegistrationsPage.test.tsx`, `NotificationsPage.test.tsx` (Attendee block), `EventRegistration.test.tsx`, `CancelEventPanel.test.tsx`, `permissions.test.ts` |
| Database | `backend/SUPABASE_US4_6_CANCEL_EVENT.sql`, then `backend/SUPABASE_US4_6_CANCEL_REGISTRATIONS.sql` — see §6 |

---

## 1. HAPPY PATH TEST CASES

### TC-C01: The assigned Coordinator cancels (AC1, AC2)
- **Pre-conditions**: Event in Planning, assigned to Priya
- **Test Steps**: `POST /events/800/cancel` with `{"reason": "Funding was withdrawn."}`
- **Expected Result**: HTTP 200; status Cancelled; last history entry Planning → Cancelled by Priya, with a time, the reason as its note and `kind: "cancellation"` (shown as "Cancellation reason")
- **Automated**: `test_the_assigned_coordinator_cancels`, `test_the_move_is_logged_with_who_when_and_why`; frontend "lets the assigned Coordinator cancel the event, and then shows it read-only"

### TC-C02: The owning Organiser cancels, including their own Draft (AC1)
- **Automated**: `test_the_owning_organiser_cancels`, `test_the_organiser_can_cancel_their_own_draft`, `test_an_organisers_cancellation_names_them`

### TC-C03: Every open status can be cancelled (AC1)
- **Expected Result**: Submitted, Under Review, Approved, Planning, Pending Safety Check, Confirmed → 200
- **Automated**: `test_every_open_status_can_be_cancelled`, `TestTheRule`; `status.test.ts` US4.6 block

### TC-C04: Active bookings and holds are released (AC3)
- **Pre-conditions**: Requested, Confirmed, live Held, expired Held, Rejected, earlier-Cancelled bookings on the event, and a Confirmed booking on another event
- **Expected Result**: Requested, Confirmed and live Held → Cancelled with Priya, the time and the reason; the rest unchanged; the other event's booking untouched
- **Automated**: `test_every_active_booking_and_hold_is_cancelled_and_nothing_else`, `test_a_confirmed_booking_keeps_the_decision_that_confirmed_it`

### TC-C05: The freed slot can be booked again (AC3)
- **Expected Result**: Another event's request for the same venue and time is 409 `not-available` before, 201 after
- **Automated**: `test_the_freed_slot_can_be_requested_by_another_event`

### TC-C06: Equipment is released (AC3)
- **Expected Result**: Every line not already Removed → Removed, version +1, `updated_by` Priya, a "Removed" history entry; it leaves `GET /equipment-requests`
- **Automated**: `test_every_equipment_line_is_released`, `test_released_equipment_leaves_the_tech_support_queue`

### TC-C07: Everyone affected is notified (AC5)
- **Expected Result**: Organiser: `"Open House" was cancelled by Priya. Reason: …`; Venue Staff: `… so its bookings were released: Great Hall and Seminar Room 4. Reason: …`; Tech Support: `… so its equipment requests were released: 2 × Projector and 1 × Microphone. Reason: …`; all status Cancelled; Priya (the canceller) gets nothing
- **Automated**: `test_everyone_affected_is_told_but_not_the_canceller`, `test_the_coordinator_is_told_when_the_organiser_cancels`, `test_venue_staff_read_the_notice`; `NotificationsPage.test.tsx` US4.6 block

### TC-C08: Full lifecycle, Draft → Confirmed → Cancelled
- **Automated**: `test_from_draft_to_confirmed_then_cancelled`

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-C10: The cancelled event is read-only (AC2)
- **Expected Result**: Save (Organiser or Coordinator) → 409 `event-cancelled`; request a venue → 409 `event-closed`; equipment, change request, clarification, safety check, submit → 409; a waiting change request can no longer be answered; the event still reads for both
- **Automated**: `TestReadOnly`, `test_a_cancelled_event_is_read_only` (US14.2 file); frontend "shows the owning Organiser a cancelled event as read-only, with nothing waiting", "gives an editing Coordinator no form on a cancelled event"

### TC-C11: A notice that cannot be written never undoes the cancellation
- **Automated**: `test_a_notice_that_cannot_be_written_does_not_undo_the_cancellation`, `test_a_failed_read_of_what_was_released_does_not_undo_it`

### TC-C12: A flag on a released booking clears (US15.2)
- **Automated**: `test_a_flag_on_a_released_booking_is_cleared`

### TC-C13: The page asks before it cancels
- **Expected Result**: "Cancel this event…" opens a warning ("This cannot be undone…") and a reason box; "Confirm cancellation" stays disabled until a reason is typed; "Keep event" closes it and forgets the reason; a cancelled event shows "Cancelled by … on …", the reason, and "This event is read-only."
- **Automated**: `CancelEventPanel.test.tsx`

### TC-C14: Notices link only where the reader can go
- **Expected Result**: Venue Staff and Tech Support see the cancellation notice without an "Open …" link (they cannot open events); the Organiser's links to the event
- **Automated**: `NotificationsPage.test.tsx` US4.6 block

---

## 3. NEGATIVE TEST CASES

| ID | Scenario | Expected | Automated |
| --- | --- | --- | --- |
| TC-C20 | Cancel a Completed / Cancelled / Rejected event | 409 `event-completed` / `already-cancelled` / `event-rejected`; unchanged | `test_a_closed_event_is_refused_and_left_alone` |
| TC-C21 | Cancel twice | 409 "This event has already been cancelled." | `test_cancelling_twice_is_refused` |
| TC-C22 | Empty, blank or missing reason | 400 "Give a reason for cancelling this event."; unchanged | `test_a_reason_is_required`, `test_a_missing_reason_field_is_the_same_sentence` |
| TC-C23 | Another Organiser's event; an unassigned Coordinator; a Coordinator on a Draft | 404 | `TestWhoMayCancel` |
| TC-C24 | Lead, Venue Staff, Safety Officer, Tech Support | 403 "…cannot cancel events" | `test_no_other_role_may_cancel` |
| TC-C25 | Signed out; unknown or non-numeric id | 401; 404 | `test_signed_out_is_refused`, `test_unknown_event` |
| TC-C26 | Race lost in the store | 409 `invalid-transition` | `test_a_race_lost_in_the_store_is_reported_as_stale`, `TestInMemoryStore` |

## 3a. REGISTRATIONS (AC4, AC5)

| ID | Scenario | Expected | Automated |
| --- | --- | --- | --- |
| TC-C40 | Cancel an event with a Registered and a Withdrawn registration, and another event's | Registered → Event Cancelled; Withdrawn stays; the other event's untouched | `test_every_registered_registration_is_marked_event_cancelled_and_nothing_else`; DB: `test_registered_ones_become_event_cancelled_and_withdrawn_ones_stay` |
| TC-C41 | Registration settings afterwards | Closed, capacity kept; 0 places taken | `test_registration_closes_and_keeps_its_capacity` (API and DB) |
| TC-C42 | The registered Attendee | One Cancelled notice, `"Open House" has been cancelled, so your registration for it is cancelled too.`, without the reason; a withdrawn Attendee is not told | `test_registered_attendees_are_told_without_the_reason`, `test_each_attendee_is_told_once` |
| TC-C43 | The Attendee's notifications page | The notice, linking to My Registrations, not to the event | `test_an_attendee_reads_it_on_their_notifications_page`; frontend "links an Attendee to My Registrations, since they cannot open the event" |
| TC-C44 | The Attendee's My Registrations | `Event Cancelled`, no Withdraw or Register again, "There is nothing you need to do." | `test_the_attendee_sees_event_cancelled_on_my_registrations`; frontend "shows a registration the event’s cancellation ended, with nothing to do" |
| TC-C45 | The Attendee tries to withdraw afterwards | 409 `event-closed`, not `already-withdrawn` | `test_a_cancelled_registration_cannot_be_withdrawn`, `test_one_the_events_cancellation_ended_is_closed_not_withdrawn`; DB: `test_a_cancelled_registration_answers_closed_not_withdrawn` |
| TC-C46 | Someone registers afterwards | Refused: the event is not Confirmed | DB: `test_nobody_registers_afterwards` |
| TC-C47 | The Organiser's list of who registered (US20.3) | Still shown, each as Event Cancelled or Withdrawn | `test_the_organiser_still_sees_who_was_registered`; frontend "shows who was registered when the event was cancelled (US4.6)" |
| TC-C48 | Nobody registered | Cancels; no Attendee notice | `test_an_event_nobody_registered_for_tells_no_attendee`, `test_an_event_nobody_registered_for_releases_none` |
| TC-C49 | Reading the ended registrations fails after the cancellation | Still 200 and Event Cancelled; only the Attendees' notices are lost | `test_a_failed_read_of_the_registrations_does_not_undo_it` |
| TC-C50 | The cancel box's warning | Says every registration is marked Event Cancelled, and that Attendees are told without the reason | `CancelEventPanel.test.tsx` |
| TC-C51 | A refused cancellation | No registration changes | DB: `test_a_refused_cancellation_ends_nothing` |

## 4. BOUNDARY TEST CASES

| ID | Boundary | Expected | Automated |
| --- | --- | --- | --- |
| TC-C30 | Reason of 2000 / 2001 characters | 200 / 400 | `test_the_reason_has_a_limit` |
| TC-C31 | A closed event with a blank reason | 409 first (status before reason) | `test_a_closed_event_is_refused_before_the_reason_is_read` |
| TC-C32 | Event with nothing to release | 200; no Venue Staff or Tech Support notice | `test_an_event_with_nothing_held_still_cancels`, `test_nobody_else_is_told_when_nothing_was_released` |
| TC-C33 | One booking / one line | Singular wording | `test_one_booking_and_one_line_read_in_the_singular` |

## 5. The database function

`cancel_event(p_event_id, p_expected_status, p_actor_id, p_reason)` returns
`{"bookings": [ids], "equipment": [ids], "registrations": [ids]}`, or NULL when it
changes nothing (missing event, status moved, closed status, blank reason, or an
actor who neither owns the event nor is its assigned Coordinator). **Automated**:
`TestSupabaseStore`, which also reads an answer from before the registrations
script (no `"registrations"`) as none released.

`SUPABASE_US4_6_CANCEL_EVENT.sql` also relaxes `venue_bookings_decision_recorded` (a
Cancelled booking may keep its decision) and lets the two US19 equipment triggers
release a cancelled event's lines, and nothing else.

`SUPABASE_US4_6_CANCEL_REGISTRATIONS.sql` adds the `Event Cancelled` registration
status, redefines `cancel_event` with the registration step and closing registration
(nothing else in it changes), and redefines US20.2's `withdraw_registration` so an
Event Cancelled registration answers `closed`. Its SQL Editor check is
`TEST_US4_6_CANCEL_REGISTRATIONS.sql`, which saves nothing.

## 6. Database checks (run manually in the Supabase SQL editor)

Applied to the live project on 2026-10-21; `cancel_event` answers NULL for an event
that does not exist.

**`backend/TEST_US4_6_CANCEL_EVENT.sql` runs all of the checks below in one go**:
paste it into the SQL Editor and run it. It builds its own users, venue, events,
bookings and equipment, and always ends by raising an error on purpose so that
everything is rolled back — read "US4.6 PASSED" or "US4.6 FAILED" from the
message. Nothing is saved either way.

| Check | Date | Result |
| --- | --- | --- |
| `TEST_US4_6_CANCEL_EVENT.sql` against the live Supabase project | 2026-10-21 | **US4.6 PASSED - all 20 checks**; rolled back |
| `SUPABASE_US4_6_CANCEL_REGISTRATIONS.sql` applied twice to a local Postgres built from every earlier script | 2026-10-23 | Applied cleanly both times. `TEST_US4_6_CANCEL_EVENT.sql` still **PASSED - all 20 checks** against the new `cancel_event`; `TEST_US4_6_CANCEL_REGISTRATIONS.sql` **PASSED - all 9 checks**; `test_registration_db.py` 41 passed. With the registrations update removed, the SQL check (2 checks) and the DB test fail |
| Backend `ruff check`, `compileall`, `pytest` | 2026-10-23 | Clean; 1969 passed, 2 skipped (the opt-in database files) |
| Frontend `oxlint`, `tsc -b`, `vitest`, `build` | 2026-10-23 | Clean; 1043 passed. One 5-second timeout under full-suite load (`NewEventPage`) passes alone |
| `SUPABASE_US4_6_CANCEL_REGISTRATIONS.sql` on the live Supabase project | — | **Not yet**: run it after the US20.1 and US20.2 scripts, then `TEST_US4_6_CANCEL_REGISTRATIONS.sql`, and record the result here |
| Backend `ruff check`, `compileall`, `pytest` | 2026-10-21 | 1693 passed |
| Frontend `oxlint`, `build`, `vitest` | 2026-10-21 | Clean; 917 passed. Unrelated: the `UnassignedQueuePage` date test fails on a non-US locale, and one 5-second timeout under full-suite load passes alone |

The same checks by hand, with a Planning test event `:id` assigned to the
Coordinator, holding a Confirmed booking and a Requested equipment line:

1. `SELECT public.cancel_event(:id, 'Planning', :coordinator, '');` → NULL (reason required).
2. `SELECT public.cancel_event(:id, 'Planning', :venue_staff, 'x');` → NULL (not theirs to cancel).
3. `SELECT public.cancel_event(:id, 'Planning', :coordinator, 'Test');` → `{"bookings": [..], "equipment": [..]}`; the event is Cancelled with one new `status_changes` row; the booking is Cancelled and keeps `decided_at`; the line is Removed with a "Removed" history row.
4. Run step 3 again → NULL.
5. `UPDATE public.equipment_requests SET quantity = 2 WHERE event_id = :id;` → error "only change while the event is Planning".

# Test Cases for US4.1, US4.2: View Event Status and Status Transitions

> **US4.1** As an Event Organiser or Event Coordinator, I want to see each event's
> status wherever the event appears, so that I always know where a request stands.
>
> **US4.2** As an Event Organiser, I want a new event to start as a Draft that I can
> save and then submit once, with every status change recorded, so that I know
> what happened to it, when and by whom.

## Acceptance Criteria

| # | Criterion | Status |
| --- | --- | --- |
| US4.1 AC1 | Every event shows one status from the agreed set, wherever it appears | Done — list and detail page |
| US4.1 AC2 | The Organiser sees the status of the events they own; a Coordinator sees submitted requests | Done |
| US4.2 AC1 | A new event is created as Draft | Done |
| US4.2 AC2 | Saving a Draft keeps it a Draft | Done — and writes no history entry |
| US4.2 AC3 | Submit moves Draft → Submitted exactly once; a second attempt is refused with a reason | Done |
| US4.2 AC4 | Every status change records who made it and when, shown as a timeline | Done |

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

### Team assumptions (not customer-confirmed)
- **The status labels are declared once** (`EVENT_STATUSES` in `status.ts`, the
  `event_status` enum in Postgres) and every page reads them from there. The agreed
  nine became ten when US4.4 added Pending Safety Check.
- **A Draft is private to its Organiser.** A Coordinator sees an event only once it
  is submitted. Which Coordinator sees which events was narrowed later (US8.1,
  US8.6); those rules have their own tests.
- **Someone else's event reads as missing** (404), not forbidden (403), so the answer
  does not confirm that the event exists.
- **A save is not a status change**, so it writes no history entry.
- **The "Created as Draft" entry** comes from the event's own `created_at` and
  Organiser rather than a stored row, because `status_changes.old_status` cannot be
  empty.
- **The server enforces every rule.** The browser checks the same rules first only to
  save a round trip.
- **Times are shown in Singapore time.** `created_at`, `updated_at` and `changed_at`
  are stored as UTC and converted for display (`formatRecordedAt`).

## Workflow Visualization

```
Organiser: New event ── POST /events ──► Draft  (history: "Created as Draft", who, when)
                                          │
              Save (PUT /events/{id}) ────┤  stays Draft, no history entry
                                          │
              Submit (POST /events/{id}/submit)
                                          ▼
                                      Submitted  (history: Draft → Submitted, who, when)
                                          │
              Submit again ──► 409 already-submitted
                                          │
              later stories move it on: Under Review, Approved, Planning,
              Pending Safety Check, Confirmed, Completed, Cancelled, Rejected

Who sees it:  Organiser → their own events, every status
              Coordinator → submitted events only (never a Draft)
```

## Test Files

| Layer | File |
| --- | --- |
| Backend | `backend/tests/test_events.py` — `TestCreating`, `TestVisibility`, `TestSaving`, `TestSubmitting`, `TestSprintOneReachableStatuses` |
| Frontend | `status.test.ts` (US4.1 and US4.2 blocks), `StatusBadge.test.tsx`, `StatusTimeline.test.tsx`, `EventsPage.test.tsx`, `EventDetailPage.test.tsx`, `NewEventPage.test.tsx`, `eventsStore.test.ts` (`createEvent`, `saveEvent`, `submitEvent`) |

---

## 1. HAPPY PATH TEST CASES

### TC-ES01: The status shows wherever the event appears (US4.1 AC1)
- **Expected Result**: every row of the events list and the event page carry a status badge; the label is one of the ten, each with its own style
- **Automated**: frontend "carries exactly the agreed statuses, in order", "renders every status with its own modifier class", "shows a status badge on every event in the list"

### TC-ES02: An Organiser sees their own events (US4.1 AC2)
- **Pre-conditions**: Dylan (Organiser) owns an event
- **Test Steps**: `GET /events`, `GET /events/{id}` as Dylan
- **Expected Result**: the event is listed and opens, with its status
- **Automated**: `test_an_organiser_sees_their_own_event`; frontend "shows an Organiser the events they own"

### TC-ES03: A Coordinator sees submitted events, with every field (US4.1 AC2)
- **Expected Result**: a submitted event is listed and opens for a Coordinator, every field read-only, with the Organiser's name
- **Automated**: `test_a_coordinator_sees_submitted_events_but_not_drafts`, `test_a_coordinator_can_open_a_submitted_event_and_see_every_field`; frontend "shows every captured field as read-only text to a Coordinator", "names the organiser for a Coordinator, who is looking across owners"

### TC-ES04: A new event starts as a Draft (US4.2 AC1)
- **Test Steps**: `POST /events` as an Organiser
- **Expected Result**: 201, status Draft; the Organiser is taken from the session, not from the request body
- **Automated**: `test_a_new_event_starts_as_a_draft`, `test_the_organiser_is_taken_from_the_session_not_the_request`; frontend "posts the draft and returns the created event", "never sends an organiser — the server takes it from the session"

### TC-ES05: Saving a Draft keeps it a Draft (US4.2 AC2)
- **Test Steps**: change the title, `PUT /events/{id}`
- **Expected Result**: 200; the title changed; status still Draft; no new history entry
- **Automated**: `test_saving_edits_content_and_leaves_the_status_alone`, `test_saving_writes_no_history_entry`, `test_owner_can_edit_their_draft`; frontend "puts the draft to the event"

### TC-ES06: Submit moves Draft → Submitted, with who and when (US4.2 AC3, AC4)
- **Test Steps**: `POST /events/{id}/submit` as the owning Organiser
- **Expected Result**: 200, status Submitted; the last history entry is Draft → Submitted by Dylan, with a time
- **Automated**: `test_an_organiser_submits_their_draft`, `test_the_submission_is_recorded_with_who_and_when`; frontend "submits the newly created event when Submit is clicked", "posts to the submit route", "allows the owning Organiser to submit a Draft"

### TC-ES07: The event page shows the whole history as a timeline (US4.2 AC4)
- **Expected Result**: "Status history" opens with "Created as Draft", then each change in order, each with who and when in Singapore time (e.g. stored `2026-10-13T09:00:00` shows as `13 Oct 2026, 17:00`)
- **Automated**: `test_the_history_opens_with_the_creation_entry`; frontend "shows the full status history, not just the current status", "keeps status history about event transitions for %s", "shows event status transitions in order", "shows when each change was made, in Singapore time", "shows when the event was created, in Singapore time"

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-ES10: The server refuses on its own account
- **Expected Result**: every "cannot" in this document is refused by the API, whatever the page shows
- **Automated**: all of `test_events.py` asserts against requests, not buttons

### TC-ES11: Someone else's event reads as missing
- **Expected Result**: another Organiser's event is not listed, and opening it directly is 404, not 403
- **Automated**: `test_an_organiser_does_not_see_another_organisers_event`, `test_an_event_that_is_not_yours_reads_as_missing_not_forbidden`; frontend "hides another Organiser’s event"

### TC-ES12: The list says what is going on
- **Expected Result**: an Organiser with no events is told what to do next; a failed load says so instead of showing "no events"; an untitled, undated Draft is labelled without inventing details
- **Automated**: frontend "tells an Organiser with no events what to do next", "says the list could not be loaded rather than showing \"no events\"", "labels an untitled and undated draft without inventing stored details"

### TC-ES13: Times are shown in Singapore time
- **Expected Result**: "Updated …" on the list and "Created …" on the event page convert the stored UTC time (`2026-10-22T15:51:40` → `22 Oct 2026, 23:51`)
- **Automated**: frontend "shows when each event was last updated, in Singapore time", "shows when the event was created, in Singapore time"; `status.test.ts` "recorded times, shown in Singapore time"

### TC-ES14: The browser never tells the server its role
- **Expected Result**: the list request carries only the session token; the server works out the role
- **Automated**: frontend "asks the API without telling it which role is asking", "does not tell the server which role is asking"

---

## 3. NEGATIVE TEST CASES

| ID | Scenario | Expected | Automated |
| --- | --- | --- | --- |
| TC-ES20 | Submit an event twice | 409 `already-submitted`, "This event has already been submitted. An event can only be submitted once." | `test_submitting_twice_is_refused_with_a_reason`; frontend "refuses a second submit on an already-submitted event", "turns a second submit into a rule error carrying the reason" |
| TC-ES21 | A Coordinator submits an event | 403, "… cannot submit events for approval …" | `test_a_coordinator_cannot_submit`; frontend "refuses anyone who does not own the event" |
| TC-ES22 | A Coordinator creates an event | 403, "… cannot create events …" | `test_a_coordinator_cannot_create_an_event`; frontend "lets only an Organiser create an event" |
| TC-ES23 | A Coordinator opens or edits a Draft | Not listed; 404 `event_not_found` when opened or saved directly | `test_a_coordinator_cannot_open_a_draft_directly`, `test_a_coordinator_cannot_open_a_draft_to_edit_it`; frontend "hides Draft events from Coordinators", "does not render a Draft if an invalid API response returns one to a Coordinator" |
| TC-ES24 | The Organiser edits their event after submitting it | 409 `change-request-required` (changes go through US11.1) | `test_owner_cannot_edit_their_submitted_event_directly`, `test_non_owner_without_edit_permission_cannot_edit` |
| TC-ES25 | Submit with no title or no date | Refused | `test_submission_still_needs_a_title`, `test_submission_still_needs_a_date`; frontend "still requires a title and date when submitting" |
| TC-ES26 | End time before start time | Refused | `test_an_end_time_before_the_start_time_is_refused`, `test_editing_an_event_rejects_an_end_not_after_the_start` |
| TC-ES27 | Unknown id; an id that is not a number | 404, not a crash | `test_an_unknown_event_is_a_404`, `test_an_id_that_is_not_a_number_is_a_404_not_a_crash`; frontend "reads a 404 as \"no such event\" rather than throwing" |
| TC-ES28 | Signed out | 401 | `test_signing_in_is_required` |

## 4. BOUNDARY TEST CASES

| ID | Boundary | Expected | Automated |
| --- | --- | --- | --- |
| TC-ES30 | Start and end at the same time | Refused (the end must be after the start) | `test_editing_an_event_rejects_equal_start_and_end_times` |
| TC-ES31 | Title or purpose one character over the column | Refused | `test_a_title_longer_than_the_column_is_refused`, `test_a_purpose_longer_than_the_column_is_refused` |
| TC-ES32 | Attendance 0 / blank / negative | Kept as 0 / kept as empty, not 0 / refused | `test_a_zero_attendance_is_enough_content_for_a_draft`, `test_no_attendance_is_not_the_same_as_an_attendance_of_zero`, `test_attendance_cannot_be_negative`; frontend "keeps an attendance of zero, which is not the same as leaving it blank" |
| TC-ES33 | Submit with a start date in the past | Refused | `test_submission_rejects_a_past_start_date` |
| TC-ES34 | Statuses these two stories can produce | Only Draft and Submitted; later statuses belong to later stories | `test_only_draft_and_submitted_are_produced`; frontend "refuses statuses beyond Draft, which are out of Sprint 1 scope" |

The other submit checks (purpose, attendance, the US2.1 needs) belong to US2.1 and
are in its tests.

## 5. Recorded results

| Check | Date | Result |
| --- | --- | --- |
| Backend `pytest` on the files above | 2026-10-23 | 54 passed |
| Frontend `vitest` on the files above | 2026-10-23 | 166 passed |

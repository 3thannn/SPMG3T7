# Test Cases for US7.3: Request Clarification or Amendment

> As an Event Coordinator, I want to ask the Organiser for more information or a
> change to a submitted event, so that I can review it with what I need.

## Acceptance Criteria

| # | Criterion | Status |
| --- | --- | --- |
| AC1 | The Coordinator attaches a message to the event | Done |
| AC2 | The event's status moves to Under Review | Done — for a Submitted or Under Review event. Since US11.2 a Coordinator can also question a later-stage change request, and that event keeps its status |
| AC3 | The message is visible to the Organiser | Done — in the event's status history |
| — | The Organiser's reply | Out of scope: that is US11.1 |

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

### Team assumptions (not customer-confirmed)
- **No new table.** The message goes in `status_changes.notes`, on the row that
  records the move to Under Review. The Organiser already reads the event's
  history, so the message reaches them with no separate delivery. Automatic
  entries have no note, which is how a request is told apart from a plain status
  change.
- **Allowed from Submitted and from Under Review**, so a Coordinator can ask a
  follow-up question. A decided event answers 409 `already-decided`. A Draft
  answers 404, because a Coordinator cannot see one.
- **Only the assigned Coordinator may ask** (since US8.1). The route uses the
  shared rule for who may read an event, so another Coordinator gets 404. The story
  first said any Coordinator could ask; that was narrowed when assignment arrived.
- **The message is required**, trimmed, and at most 2,000 characters.
- **A stale request never undoes a decision.** If the event was decided after the
  page loaded, the request is refused and nothing is written.

## Workflow Visualization

```
Coordinator (assigned) on a Submitted or Under Review event
   │  types a message and sends it
   ▼
POST /events/{id}/clarification {"message": "..."}
   ├─ empty / spaces / missing / > 2000 chars ──► 400, status unchanged
   ├─ Approved, Planning, …, Rejected ──────────► 409 already-decided
   ├─ Draft, not theirs, unknown ───────────────► 404
   └─ ok ──► Under Review; history entry: who, when, the message (note)
                │
Organiser opens the event ──► sees "Under Review" and the Coordinator's request
                              in the status history, attributed and timestamped
```

## Test Files

| Layer | File |
| --- | --- |
| Backend | `backend/tests/test_event_clarification.py` |
| Frontend | `EventClarification.test.tsx`, `status.test.ts` ("status audit notes", "falls back to the US7.3/US7.1 reading when the kind is empty") |

---

## 1. HAPPY PATH TEST CASES

### TC-CL01: The Coordinator attaches a message (AC1)
- **Pre-conditions**: Event submitted and assigned to the Coordinator
- **Test Steps**: `POST /events/{id}/clarification` with `{"message": "Please confirm the catering budget."}`
- **Expected Result**: 200; the message is the note on the new history entry, exactly as written apart from surrounding spaces
- **Automated**: `test_a_coordinator_can_attach_a_message`, `test_the_message_is_recorded_on_the_status_change`, `test_the_message_is_kept_exactly_as_written`; frontend "offers a Coordinator the request form on a submitted event", "sends what was typed"

### TC-CL02: The status moves to Under Review (AC2)
- **Expected Result**: status Under Review; the entry records who asked and when; earlier history is kept; the page says "Request sent" and that the event is "now Under Review"
- **Automated**: `test_the_status_moves_to_under_review`, `test_the_request_is_attributable_and_timestamped`, `test_the_earlier_history_is_kept`; frontend "says the request was sent and names the new status", "clears the box once the request is away"

### TC-CL03: The Organiser sees the request (AC3)
- **Test Steps**: open the event as its Organiser
- **Expected Result**: the status is Under Review; the history shows the request, labelled as a request and attributed to the Coordinator; the event is still in both the Organiser's and the Coordinator's lists
- **Automated**: `test_the_owning_organiser_can_read_the_message`, `test_the_organiser_sees_the_new_status`, `test_the_event_stays_in_the_organisers_list`, `test_the_event_stays_in_the_coordinators_list`; frontend "shows the request to the Organiser it was written for", "names it as a request rather than leaving it as loose text", "attributes the request to the Coordinator who asked", "shows the Organiser the event is now under review"

### TC-CL04: A follow-up question (AC1, AC2)
- **Test Steps**: ask again while the event is Under Review
- **Expected Result**: 200; a second request entry; still Under Review; the page shows both
- **Automated**: `test_asking_again_adds_a_second_request`, `test_a_second_request_stays_under_review`, `test_an_event_under_review_may_be_queried_again`; frontend "offers it on an event already under review, so a second question is possible", "shows more than one request when a second question was asked"

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-CL10: A request is told apart from a plain status change
- **Expected Result**: automatic entries carry no note and show no message block
- **Automated**: `test_an_automatic_entry_carries_no_message`; frontend "leaves automatic entries without a message block"; `status.test.ts` "distinguishes rejection reasons from clarification requests"

### TC-CL11: A stale request cannot undo a decision
- **Pre-conditions**: the event is approved after the Coordinator's page loaded
- **Expected Result**: 409 `invalid-transition`; the event stays Approved; the stale message is not written
- **Automated**: `test_a_concurrent_decision_cannot_be_undone_by_a_stale_clarification`

### TC-CL12: A refusal keeps what was typed
- **Expected Result**: when the server refuses, the box keeps the message and the reason is shown; any other failure says something useful
- **Automated**: frontend "keeps what was typed when the server refuses", "says something useful when the request fails for another reason"

### TC-CL13: The route only reports what the rule decides
- **Expected Result**: Submitted and Under Review may be queried; a Draft reads as not yet submitted; every other status reads as decided
- **Automated**: `TestTheRuleOnItsOwn`

---

## 3. NEGATIVE TEST CASES

| ID | Scenario | Expected | Automated |
| --- | --- | --- | --- |
| TC-CL20 | An Organiser asks | 403 `forbidden`; the page offers no form | `test_an_organiser_cannot_request_clarification`; frontend "does not offer the form to the Organiser, who answers rather than asks" |
| TC-CL21 | Venue Staff ask | 403; they see none of it in the page | `test_venue_staff_cannot_request_clarification`; frontend "shows Venue Staff none of this, since the event is not theirs to see" |
| TC-CL22 | Signed out, or signed out since | 401 | `test_it_needs_a_session`, `test_signing_out_is_enough_to_lose_the_ability` |
| TC-CL23 | Empty message, only spaces, or no `message` field | 400 `invalid_event`, "Say what you need from the Organiser."; status unchanged | `test_an_empty_message_is_refused`, `test_a_message_of_only_spaces_is_no_message`, `test_a_missing_message_field_is_refused`, `test_a_refused_message_does_not_move_the_status`; frontend "will not send an empty request", "will not send a request of only spaces" |
| TC-CL24 | A decided event (e.g. Approved) | 409 `already-decided`, "This event has already been decided, so it is no longer under review."; the page explains instead of offering the form | `test_a_decided_event_is_no_longer_under_review`; frontend "explains rather than offers when the event is already decided" |
| TC-CL25 | A Rejected event | 409 | `test_a_rejected_event_is_refused_too` |
| TC-CL26 | A Draft | 404 (a Coordinator cannot see one) | `test_a_draft_is_not_reviewable` |
| TC-CL27 | Unknown id; an id that is not a number | 404 | `test_an_event_that_does_not_exist`, `test_an_id_that_is_not_a_number` |
| TC-CL28 | A Coordinator the event is not assigned to | 404 | **Not automated for this route.** `_DISABLED_test_non_assigned_coordinator_cannot_request_clarification` (`test_coordinator_assignment.py`) is switched off. The shared rule it relies on is covered by `test_non_assigned_coordinator_cannot_view` (`test_lead_assignment.py`) |

## 4. BOUNDARY TEST CASES

| ID | Boundary | Expected | Automated |
| --- | --- | --- | --- |
| TC-CL30 | Message over 2,000 characters | 400, "Keep the request to 2000 characters or fewer." | `test_an_overlong_message_is_refused_with_a_sentence` |
| TC-CL31 | Spaces around the message | Trimmed before it is stored and sent | `test_surrounding_space_is_trimmed`; frontend "trims the message rather than sending the spaces" |
| TC-CL32 | Asking from Submitted / from Under Review | Both allowed | `test_a_submitted_event_may_be_queried`, `test_an_event_under_review_may_be_queried_again` |

`test_any_coordinator_may_ask_not_only_an_assigned_one` predates US8.1. Its event is
now assigned to the Coordinator who asks, so it checks the assigned Coordinator, not
"any" Coordinator.

## 5. Recorded results

| Check | Date | Result |
| --- | --- | --- |
| Backend `pytest` on the files above | 2026-10-23 | 34 passed |
| Frontend `vitest` on the files above | 2026-10-23 | 73 passed |

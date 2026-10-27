# Test Cases for US17.2: Safety Officer Records a Decision

> As a Safety Officer, I want to approve, reject, or request changes to an
> event's safety arrangements, so that only safe events move into preparation.

## Acceptance Criteria

| # | Criterion |
| --- | --- |
| AC1 | Approve → event moves to Confirmed |
| AC2 | Request changes → back to Planning; note required; affected venue/equipment arrangements flagged for re-review; assigned Coordinator notified (US10.2) |
| AC3 | Reject → reason required. Assumption: back to Planning with the reason |
| AC4 | Every decision is timestamped and attributable (US4.2 audit pattern) |
| AC5 | An event coming back into Pending Safety Check needs a fresh decision |

### Team assumptions (not customer-confirmed)
- **Preparation** = our Confirmed status (US4.4's assumption).
- **Reject** returns the event to Planning, as the story assumes; it does not end the
  event. What tells it apart from a request for changes is the `safety_reviews` record
  and the Coordinator's notice, not the status.
- **Affected arrangements** are chosen by the Safety Officer from what the US17.1 review
  shows: bookings that hold their venue and Reserved equipment. Flagging is optional; a
  request for changes about, say, attendance may flag nothing.
- **Re-review** is the assigned Coordinator's: they mark each flag re-reviewed, and an
  open flag stops the event being sent for its check again (US4.4 readiness).
- **Rejection notice.** US10.2 lists only "requests changes", but a rejected event also
  lands back on the Coordinator's desk, so they get a `safety-rejected` notice too.
- **Fresh decision** is enforced twice: a decision is only possible while the event is
  Pending Safety Check, and it is pinned to the stay the Safety Officer reviewed
  (`checkStartedAt` = the review's `waitingSince`). A stale tab cannot decide a
  resubmission.

## Test Files

| Layer | File |
| --- | --- |
| Backend | `backend/tests/test_safety_decision_us17_2.py` |
| Frontend | `frontend/src/components/SafetyCheckPanel.test.tsx` (US17.2 blocks), `frontend/src/eventsStore.test.ts` (US17.2 block), `frontend/src/pages/EventDetailPage.test.tsx` (Safety Officer approval) |
| Database | `backend/SUPABASE_US17_2_SAFETY_DECISIONS.sql`, verified against PostgreSQL (see TC-D01–D06) |

---

## 1. HAPPY PATH

### TC-S01: Approve (AC1)
- **Pre-conditions**: event 700 Pending Safety Check since 2099-01-02 10:00, one Confirmed booking, one Reserved projector line
- **Test Steps**: Safety Officer clicks **Approve safety check**
- **Expected Result**: `POST /events/700/safety-check/approve` with `checkStartedAt`; event Confirmed; nobody notified
- **Automated**: `TestApprove`; frontend "approves the submission it was shown"

### TC-S02: Request changes, flagging arrangements (AC2)
- **Test Steps**: type "Add a second fire exit.", tick Great Hall and Projector × 2, click **Request changes**
- **Expected Result**: event Planning; history note "Add a second fire exit." labelled "Sent back by Safety Officer"; two open flags; Coordinator notice `safety-changes`: *…: Add a second fire exit. 2 arrangements flagged for re-review.*
- **Automated**: `test_back_to_planning_with_the_note`, `test_the_affected_arrangements_are_flagged`, `test_the_assigned_coordinator_is_told`; frontend "requests changes with the trimmed note and the arrangements flagged"

### TC-S03: Reject with a reason (AC3)
- **Test Steps**: choose **Reject**, type "Venue unsafe.", click **Reject safety check**
- **Expected Result**: event Planning with the reason in its history; decision recorded as `rejected`; Coordinator notice `safety-rejected`; no flag picker shown
- **Automated**: `TestReject`; frontend "rejects with a reason, and flags nothing"

### TC-S04: The decision record (AC4)
- **Expected Result**: `GET /events/700/safety-decisions` → outcome, note, `decidedByName` "Alex", `decidedAt`, `checkStartedAt`; the `status_changes` row has the Safety Officer's id and time
- **Automated**: `TestDecisionRecord`

### TC-S05: Coordinator re-reviews flags, then resends (AC2, AC5)
- **Test Steps**: Coordinator opens the Planning event, sees the request and its flags, clicks **Mark Great Hall re-reviewed**, then **Send for safety check**
- **Expected Result**: readiness says `safety-flags-open` until every flag is re-reviewed; then the send is allowed; the event re-enters the queue undecided
- **Automated**: `TestReReview`, `test_a_returned_event_comes_back_undecided`; frontend "marks a flag re-reviewed, then re-checks whether the event is ready"

### TC-S06: Fresh decision on the resubmission (AC5)
- **Test Steps**: after TC-S05, approve with the *first* stay's `checkStartedAt`; then with the current review's
- **Expected Result**: first → 409 `check-moved-on` and nothing changes; second → Confirmed; both decisions kept, each with its own `checkStartedAt`
- **Automated**: `TestFreshDecision`

## 2. NEGATIVE AND BOUNDARY

| ID | Scenario | Expected | Automated |
| --- | --- | --- | --- |
| TC-S10 | Request changes / reject with empty or whitespace note | 400, event unchanged | `test_a_note_is_required`, `test_a_reason_is_required` |
| TC-S11 | Note of 2,001 characters | 400 | `test_the_note_has_a_limit`, `test_the_note_has_a_limit_whatever_the_outcome` |
| TC-S12 | Flags sent with approve or reject | 400 "Only a request for changes flags…" | `test_an_approval_flags_nothing`, `test_a_rejection_flags_nothing` |
| TC-S13 | Flag a cancelled booking, another event's booking, an unknown id, or a still-Requested line | 400 | `test_a_booking_not_in_the_review_cannot_be_flagged`, `test_equipment_not_in_the_review_cannot_be_flagged` |
| TC-S14 | Coordinator, Organiser, Lead, Venue Staff decide | 403 | `test_only_the_safety_officer` |
| TC-S15 | Safety Officer decides a Planning event / unknown id | 404 | `test_only_while_pending`, `test_an_unknown_event` |
| TC-S16 | Decided twice / race lost in the store | 404 once Confirmed; 409 "already decided" | `test_a_check_decided_twice_is_refused`, `test_a_race_lost_in_the_store_is_reported` |
| TC-S17 | `checkStartedAt` not a timestamp | 400 | `test_a_check_time_that_is_not_a_time_is_a_bad_request` |
| TC-S18 | Resolve a flag twice / unknown / another event's / non-numeric id | 409 / 404 / 404 / 404 | `TestReReview` |
| TC-S19 | Resolve a flag when the event is not Planning | 409 `not-planning`, flag stays open | `test_only_while_planning` |
| TC-S20 | Another Coordinator reads decisions; Organiser / Venue Staff / Tech Support read them | 404; 403 | `test_another_coordinator_cannot_read_them`, `test_nobody_else_reads_them` |
| TC-S21 | Flagged booking or line deleted later | still listed, described as no longer existing | `test_a_flagged_arrangement_that_has_gone_is_still_described` |
| TC-S22 | Page: decision controls before the review loads / if it fails | disabled; error with **Try again** | frontend "locks the decision until…", "says when the review cannot be loaded…" |
| TC-S23 | US4.4 `/return` route | same as request changes, recorded as `changes-requested` | `test_us4_4s_return_route_is_the_same_move` |

## 3. DATABASE (`SUPABASE_US17_2_SAFETY_DECISIONS.sql`)

Run against PostgreSQL 18 on a minimal schema with US4.4's script applied first, then
this script twice.

| ID | Scenario | Expected |
| --- | --- | --- |
| TC-D01 | Apply the script twice | No errors (idempotent) |
| TC-D02 | `record_safety_decision` with: bad outcome; blank reason; no note on changes; flags on approve/reject; a non–Safety Officer; another stay's time; another event's booking; unknown line; event not pending | NULL each time, event unchanged |
| TC-D03 | Request changes with the booking flagged twice and one line | One decision; event Planning; audit row with the trimmed note; two flags (booking de-duplicated) |
| TC-D04 | Second decision on the same check | NULL |
| TC-D05 | `send_event_to_safety_check` with an open flag; after resolving it | FALSE; TRUE |
| TC-D06 | Insert a rejection without a note; a flag with no target; a resolved time without a resolver; notice kinds | Each refused by its CHECK; `safety-rejected` accepted, unknown kind refused |

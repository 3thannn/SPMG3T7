# Test Cases for US10.2: Coordinator Notifications

> As an Event Coordinator, I want to be notified about events that need my
> attention, so that I don't miss assignments or booking problems.

## Acceptance Criteria

| # | Criterion |
| --- | --- |
| AC1 | A notification is created for the relevant Coordinator when an event is assigned or reassigned to/away from them (US8.3, US8.4) |
| AC2 | … when a tentative hold is about to expire or has expired (US14.4) |
| AC3 | … when a booking is hit by venue unavailability or a setup/turnaround change (US12.2, US15.2) |
| AC4 | … when the Safety Officer requests changes (US17.2) |
| AC5 | Same unread/read list and toggle as US10.1, reusing the notifications table with a recipient field |
| AC6 | In-app only, no email/push |

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

**Dependency note.** Only assignment (US8.3) exists as a route today. The
triggers for AC1 (reassignment), AC2, AC3 and AC4 are `notify_*` functions in
`app/notifications.py`, ready for US8.4, US14.4, US12.2/US15.2 and US17.2 to
call. Their test cases call those functions directly, the way those stories
will. Each gets an end-to-end case once its story lands.

| Trigger | Function | Called from |
| --- | --- | --- |
| Assigned (US8.3) | `notify_assigned(event)` | `POST /events/{id}/assign` (live) |
| Reassigned (US8.4) | `notify_reassigned(event, previous_id, new_id)` | pending US8.4 |
| Hold expiring / expired (US14.4) | `notify_hold_expiring(event, venue, when)` / `notify_hold_expired(event, venue)` | Written by US14.4's scheduled sweep (`sweep_tentative_holds`, SQL) in these exact words; the Python functions are the wording it is checked against |
| Booking conflict (US12.2, US15.2) | `notify_booking_conflict(event, venue, reason)` | pending US12.2, US15.2 |
| Safety changes (US17.2) | `notify_safety_changes(event, notes, flagged)` | `POST /events/{id}/safety-check/request-changes` (live) |

## Workflow Visualization

```
Lead assigns event ──► event stored (Submitted → Under Review)
  (or US8.4/14.4/            │
   12.2/15.2/17.2            ▼
   stores its change)   notify_*(event)  ──► recipient = event's Coordinator
                             │                 (none assigned → no notice)
                             ▼
                   notifications row (user_id, kind, message, status NULL)
                             │          write fails → logged, request still succeeds
                             ▼
Coordinator ──► Notifications link (unread count) ──► list: unread first, newest first
                                                        │
                                                        ▼
                                          Mark as read / Mark as unread
```

## Test Files

| Layer | File |
| --- | --- |
| Backend | `backend/tests/test_coordinator_notifications.py` (TC-CN01–CN20) |
| Frontend | `frontend/src/pages/NotificationsPage.test.tsx` (TC-CF01–CF05), `frontend/src/components/TopNav.test.tsx` (TC-CF06) |
| Updated for US10.2 | `test_notifications.py` TC-N08, TC-N15; `test_access_enforcement.py`; `permissions.test.ts` TC-F17; `TopNav.test.tsx` TC-F16 |

---

## 1. HAPPY PATH TEST CASES

### TC-CN01: Assignment notifies the Coordinator (AC1)
- **Pre-conditions**: Organiser has a Submitted event "Faculty Welcome Night"; Coordinator (id 2) has no notices
- **Test Steps**:
  1. As the Lead, `POST /events/{id}/assign` with `{"coordinatorId": "2"}`
  2. As the Coordinator, `GET /notifications`
- **Expected Result**: One unread notice, `kind` = `assigned`, `status` = null, message `You were assigned "Faculty Welcome Night".`, linked to the event
- **Automated**: `test_tc_cn01_assignment_notifies_the_coordinator`

### TC-CN05: Reassignment notifies both Coordinators (AC1)
- **Test Steps**: `notify_reassigned(event, 2, 99)`
- **Expected Result**: Coordinator 2 gets `unassigned`: `"Careers Fair" is no longer assigned to you.`; Coordinator 99 gets `assigned`: `You were assigned "Careers Fair".`
- **Automated**: `test_tc_cn05_reassignment_tells_both_coordinators`

### TC-CN08: Tentative hold about to expire (AC2)
- **Test Steps**: `notify_hold_expiring(event, "Main Hall", "in 24 hours")`
- **Expected Result**: Event's Coordinator gets `hold-expiring`: `The tentative hold on Main Hall for "Careers Fair" expires in 24 hours.`
- **Automated**: `test_each_trigger_notifies_the_assigned_coordinator[tc_cn08_hold_expiring]`

### TC-CN09: Tentative hold expired (AC2)
- **Test Steps**: `notify_hold_expired(event, "Main Hall")`
- **Expected Result**: `hold-expired`: `The tentative hold on Main Hall for "Careers Fair" has expired.`
- **Automated**: `test_each_trigger_notifies_the_assigned_coordinator[tc_cn09_hold_expired]`

### TC-CN10: Booking hit by venue unavailability or setup change (AC3)
- **Test Steps**: `notify_booking_conflict(event, "Main Hall", "the venue is closed for repairs that day.")`
- **Expected Result**: `booking-conflict`: `The booking of Main Hall for "Careers Fair" needs attention: the venue is closed for repairs that day.`
- **Automated**: `test_each_trigger_notifies_the_assigned_coordinator[tc_cn10_booking_conflict]`

### TC-CN11: Safety Officer requests changes (AC4)
- **Test Steps**: `notify_safety_changes(event, "Add a second fire exit.")`
- **Expected Result**: `safety-changes`: `The Safety Officer requested changes to "Careers Fair": Add a second fire exit.`
- **Automated**: `test_each_trigger_notifies_the_assigned_coordinator[tc_cn11_safety_changes]`

### TC-CN16: Coordinator marks a notice read, then unread (AC5)
- **Pre-conditions**: Coordinator has one unread `assigned` notice
- **Test Steps**:
  1. `PATCH /notifications/{id}` with `{"read": true}`
  2. `PATCH /notifications/{id}` with `{"read": false}`
- **Expected Result**: HTTP 200 both times; `read` true then false
- **Automated**: `test_tc_cn16_a_coordinator_can_mark_a_notice_read_and_unread`

### TC-CN17: Unread first, then newest (AC5)
- **Pre-conditions**: Two notices, the newer one marked read
- **Expected Result**: `GET /notifications` lists the older unread notice before the newer read one
- **Automated**: `test_tc_cn17_unread_first_then_newest`

### TC-CF01: Page labels each Coordinator notice by kind (AC5)
- **Expected Result**: Labels "Assigned to you", "Hold expiring", "Hold expired", "Booking problem", "Safety changes", "Reassigned"; no status badge
- **Automated**: `NotificationsPage.test.tsx` › TC-CF01

### TC-CF02: A Coordinator notice opens its event (AC5)
- **Expected Result**: "Open Gala" link navigates to `#/events/101`
- **Automated**: `NotificationsPage.test.tsx` › TC-CF02

### TC-CF04: Coordinator marks a notice read on the page (AC5)
- **Expected Result**: `setNotificationRead('1', true, session)` called; notice moves to the Read group
- **Automated**: `NotificationsPage.test.tsx` › TC-CF04

### TC-CF06: Coordinator gets the Notifications link with unread count (AC5)
- **Expected Result**: Nav shows Notifications with "1 unread"
- **Automated**: `TopNav.test.tsx` › TC-CF06

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-CN02: The Organiser's US10.1 notice is unaffected (AC5)
- **Test Steps**: Assign an event
- **Expected Result**: Exactly two notices: Organiser gets `event-status` (Under Review), Coordinator gets `assigned`
- **Automated**: `test_tc_cn02_the_organiser_gets_their_own_notice_not_this_one`

### TC-CN04: A failed notice does not fail the assignment
- **Pre-conditions**: Notification write raises (e.g. the migration was not run)
- **Expected Result**: Assignment still HTTP 200, event Under Review
- **Automated**: `test_tc_cn04_a_failed_notice_does_not_fail_the_assignment`

### TC-CN14: A failed write is logged, not raised
- **Expected Result**: No exception; log contains `US10.2 safety-changes notification`
- **Automated**: `test_tc_cn14_a_failed_write_is_logged_not_raised`

### TC-CN20: The Supabase store writes a valid Coordinator row (AC5)
- **Expected Result**: Insert into `notifications` with the Coordinator's `user_id`, the `kind`, `status` null and no `equipment_request_id`, as the `notifications_kind_valid` check requires; the returned notice carries the event title
- **Automated**: `test_tc_cn20_create_notice_writes_a_coordinator_row`

### TC-CF05: The page explains what a Coordinator will see
- **Expected Result**: Subtitle "Assignments and booking or safety problems…"; empty state "When an event is assigned to you…"
- **Automated**: `NotificationsPage.test.tsx` › TC-CF05

### AC6: In-app only
- **Verification**: By inspection. The notify functions only insert a `notifications` row; no email or push code path exists.

---

## 3. NEGATIVE TEST CASES

### TC-CN03: A refused assignment does not notify (AC1)
- **Test Steps**: Assign the same event twice
- **Expected Result**: Second call HTTP 409; Coordinator still has exactly one notice
- **Automated**: `test_tc_cn03_a_refused_assignment_does_not_notify`

### TC-CN18: A Coordinator sees only their own notices (AC5)
- **Pre-conditions**: A notice exists for another Coordinator (id 99)
- **Expected Result**: Coordinator 2's list is empty
- **Automated**: `test_tc_cn18_a_coordinator_sees_only_their_own_notices`

### TC-CN19: A Coordinator cannot toggle someone else's notice (AC5)
- **Expected Result**: `PATCH /notifications/{other's id}` → HTTP 404
- **Automated**: `test_tc_cn19_a_coordinator_cannot_toggle_someone_elses_notice`

### TC-N15 (updated): Roles without notifications are refused
- **Expected Result**: Coordinator Lead and Venue Staff get HTTP 403 on `GET /notifications`
- **Automated**: `test_notifications.py` › `test_tc_n15_other_roles_are_refused`

### TC-F16 / TC-F17 (updated): No Notifications link or route for other roles
- **Expected Result**: Lead and Venue Staff see no link and cannot open `/notifications`; Organiser and Coordinator can
- **Automated**: `TopNav.test.tsx` › TC-F16, `permissions.test.ts` › TC-F17

### TC-CF03: No link for an event reassigned away (AC1)
- **Expected Result**: An `unassigned` notice shows its message with no link, since the Coordinator can no longer open the event
- **Automated**: `NotificationsPage.test.tsx` › TC-CF03

---

## 4. BOUNDARY TEST CASES

### TC-CN06: Reassigning to the same Coordinator is silent (AC1)
- **Test Steps**: `notify_reassigned(event, 2, 2)`
- **Expected Result**: No notices
- **Automated**: `test_tc_cn06_reassigning_to_the_same_coordinator_is_silent`

### TC-CN07: A first assignment through reassign notifies only the new Coordinator (AC1)
- **Test Steps**: `notify_reassigned(event, None, 2)`
- **Expected Result**: One `assigned` notice for Coordinator 2; no `unassigned`
- **Automated**: `test_tc_cn07_a_first_assignment_through_reassign_only_notifies_the_new_one`

### TC-CN12: Safety changes with no notes (AC4)
- **Expected Result**: `The Safety Officer requested changes to "Careers Fair".`
- **Automated**: `test_each_trigger_notifies_the_assigned_coordinator[tc_cn12_safety_changes_without_notes]`

### TC-CN13: An event with no Coordinator notifies nobody (AC2–AC4)
- **Test Steps**: Call the hold, booking and safety functions on an unassigned event
- **Expected Result**: No notices, no error
- **Automated**: `test_tc_cn13_an_unassigned_event_notifies_nobody`

### TC-CN15: An untitled event still reads sensibly
- **Pre-conditions**: Event title is whitespace only
- **Expected Result**: `The tentative hold on Main Hall for "an untitled event" has expired.`
- **Automated**: `test_tc_cn15_an_untitled_event_still_reads_sensibly`

---

## 5. TRACEABILITY MATRIX

| AC | Test cases | Status |
| --- | --- | --- |
| AC1 assigned | TC-CN01, CN02, CN03, CN04 | ✅ Live: route calls it |
| AC1 reassigned | TC-CN05, CN06, CN07, CF03 | 🔌 Function tested; waits on US8.4 |
| AC2 | TC-CN08, CN09, CN13 | ✅ Delivered by US14.4's sweep once scheduled; see `test_cases_us14_4.md` (TC-E04, TC-E05) |
| AC3 | TC-CN10, CN13 | 🔌 Function tested; waits on US12.2, US15.2 |
| AC4 | TC-CN11, CN12, CN13 | 🔌 Function tested; waits on US17.2 |
| AC5 | TC-CN16–CN20, CF01–CF06, N15, F16, F17 | ✅ |
| AC6 | By inspection | ✅ |

## 6. TEST EXECUTION RESULTS

| Run | Date | Result |
| --- | --- | --- |
| Backend `ruff check`, `compileall`, `pytest` | 2026-10-15 | 1048 passed |
| Frontend `lint`, `build`, `vitest` | 2026-10-15 | 583 passed |
| Coverage, `app/notifications.py` | 2026-10-15 | 99%; every US10.2 line covered |
| Coverage, `NotificationsPage.tsx` | 2026-10-15 | 100% of lines |

### Live verification against Supabase (2026-10-15)
After running `SUPABASE_ADD_COORDINATOR_NOTIFICATIONS.sql` on the shared project:

| Step | Result |
| --- | --- |
| Sign in as `coordinatorlead@`, assign event 51 to `coordinator@` | HTTP 200, event Under Review |
| `coordinator@` `GET /notifications` | 0 → 1 notice: `You were assigned "E2E Test Event 1791857633050".` (unread) |
| Mark read, then unread | HTTP 200 both; read notice listed below unread ones |
| Rows in `notifications` for event 51 | id 7: Organiser, `event-status`, Under Review; id 8: Coordinator, `assigned` |
| `coordinatorlead@` `GET /notifications` | HTTP 403 |
| Backend log | No notification write errors |

# Test Cases for US4.4: Pending Safety Check Status and Transitions

> As the system, I want a Pending Safety Check stage between planning and
> preparation, so that no event moves forward without a safety sign-off.

## Acceptance Criteria

| # | Criterion |
| --- | --- |
| AC1 | New status label 'Pending Safety Check' added to US4.1's set |
| AC2 | Planning → Pending Safety Check (once all active venue bookings are Confirmed and equipment is reserved) |
| AC3 | Pending Safety Check → Confirmed (Safety Officer approves) |
| AC4 | Pending Safety Check → Planning (Safety Officer requests changes or rejects, see US17.2) |
| AC5 | Event can't reach Confirmed any other way |
| AC6 | Extends US4.3's trigger rather than replacing it |
| — | Assumption: 'preparation' in the customer brief = our Confirmed status |

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

### Team assumptions (not customer-confirmed)
- **Who moves Planning → Pending Safety Check.** The assigned Coordinator sends the
  event, and the system allows it only once the AC2 condition holds. It is not
  automatic: a multi-venue event (Week 7 change #3) would otherwise jump to the
  safety check the moment its first venue is Confirmed, before the breakout rooms
  are even requested, and then could not take any more bookings.
- **"Active" bookings** are the ones that hold a venue: Requested, Confirmed, and Held
  until its expiry. Cancelled, Rejected and expired holds are ignored. At least one
  Confirmed booking is required — an event with no venue has nothing to check.
- **"Equipment is reserved"** means every equipment line that has not been removed is
  `Reserved`. US19.3 adds that status; until it ships, any equipment line blocks the
  check (remove the lines not needed). An event with no equipment lines passes.
- Two extra blockers, so the Safety Officer never reviews something about to change:
  a Confirmed booking flagged "Conflict – review needed" (US15.2), and an unanswered
  Organiser change request (US11.1).
- **AC4 in this story** is one send-back action with a required note. US17.2 splits it
  into separate "request changes" and "reject" outcomes, adds the safety_reviews
  record and the re-review flags. The send-back already notifies the assigned
  Coordinator through US10.2's `notify_safety_changes`.
- The Safety Officer may open an event only while it is Pending Safety Check.
  US17.1 adds the venue/equipment detail to that view.

## Workflow Visualization

```
Approved ──(first venue request, US4.5)──► Planning ◄─────────────────────────┐
                                              │                               │
             Coordinator: "Send for safety check"                             │
             ready? every active booking Confirmed, none flagged,             │
                    every equipment line Reserved, no pending change request  │
                    ├── no ──► 409 with the reason; event stays Planning      │
                    ▼ yes                                                     │
                        Pending Safety Check ──── Safety Officer ─────────────┤
                                              │   "Send back to Planning"     │
                                              │   (note required) ────────────┘
                                              │   + Coordinator notified
                                              ▼ "Approve safety check"
                                          Confirmed ──(after end, US4.5)──► Completed
```

Every move writes a `status_changes` row with who and when (US4.2).

## Test Files

| Layer | File |
| --- | --- |
| Backend | `backend/tests/test_safety_check_us4_4.py` |
| Backend (US4.3 regression) | `backend/tests/test_event_decisions.py` — allowlist updated with the three new transitions |
| Frontend | `frontend/src/status.test.ts`, `frontend/src/eventsStore.test.ts`, `frontend/src/components/StatusBadge.test.tsx`, `frontend/src/components/SafetyCheckPanel.test.tsx`, `frontend/src/pages/SafetyReviewPage.test.tsx`, `frontend/src/pages/EventDetailPage.test.tsx` |
| Database | `backend/SUPABASE_ADD_SAFETY_CHECK_STATUS.sql` — see §6 |

---

## 1. HAPPY PATH TEST CASES

### TC-S01: The new label exists, in workflow order (AC1)
- **Expected Result**: `Pending Safety Check` sits between Planning and Confirmed in both the server enum and the client label set, and round-trips through `GET /events/{id}`
- **Automated**: `TestStatusLabel`; frontend `status.test.ts` (US4.1 label set, US4.4 block)

### TC-S02: The badge renders it (AC1)
- **Expected Result**: Its own colour/modifier (`status-badge-safety`), distinct from every other status
- **Automated**: `StatusBadge.test.tsx`

### TC-S03: The Coordinator sees the event is ready (AC2)
- **Pre-conditions**: Event in Planning, assigned to Priya, one Confirmed booking, no equipment lines
- **Test Steps**: `GET /events/700/safety-check`
- **Expected Result**: `{"ready": true, "reason": "", "message": ""}`; the page enables "Send for safety check"
- **Automated**: `test_readiness_says_ready`; `SafetyCheckPanel.test.tsx` "offers the send once the server says ready"

### TC-S04: Sending moves Planning → Pending Safety Check (AC2)
- **Test Steps**: `POST /events/700/safety-check` as Priya
- **Expected Result**: HTTP 200; status Pending Safety Check; last history entry Planning → Pending Safety Check by Priya with a time
- **Automated**: `test_the_assigned_coordinator_sends_a_ready_event`; frontend "lets the assigned Coordinator send a ready Planning event"

### TC-S05: The Safety Officer's queue (AC3/AC4 entry point)
- **Pre-conditions**: Events 1 and 2 entered the check on 3 Jan and 2 Jan; event 3 has no entry (falls back to `updated_at` 2 Jan 10:00); events 4 (Planning) and 5 (Confirmed)
- **Test Steps**: `GET /events/safety-check` as Alex
- **Expected Result**: `[2, 3, 1]` — only Pending Safety Check, longest waiting first; a re-sent event joins the back
- **Automated**: `TestSafetyOfficerQueue`; `SafetyReviewPage.test.tsx`

### TC-S06: Approval confirms the event (AC3)
- **Test Steps**: `POST /events/700/safety-check/approve` as Alex
- **Expected Result**: HTTP 200; status Confirmed; history Pending Safety Check → Confirmed by Alex
- **Automated**: `test_approval_confirms_the_event`; frontend "shows the Safety Officer the outcome of their approval"

### TC-S07: Sending back returns it to Planning with the note (AC4)
- **Test Data**: `{"note": "  Add a second fire marshal.  "}`
- **Expected Result**: HTTP 200; status Planning; history entry by Alex with the trimmed note and `kind: "safety-return"` (shown as "Sent back by Safety Officer"); Priya gets a notification carrying the note
- **Automated**: `test_sending_back_returns_it_to_planning_with_the_note`; `SafetyCheckPanel.test.tsx` "sends the event back with the trimmed note"; `status.test.ts` label

### TC-S08: Full lifecycle, Draft → Confirmed (AC2, AC3, AC5)
- **Steps**: create → submit → Lead assigns → approve → request venue → readiness says `venue-not-confirmed` → Venue Staff approve booking → readiness says ready → send → Safety Officer approves
- **Expected Result**: History is exactly Draft, Submitted, Under Review, Approved, Planning, Pending Safety Check, Confirmed
- **Automated**: `test_end_to_end_from_draft_to_confirmed`

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-S09: A returned event can be re-sent and needs a fresh decision (US17.2 note)
- **Automated**: `test_a_returned_event_can_be_sent_again_and_needs_a_fresh_decision`

### TC-S10: Races are reported, not overwritten
- **Expected Result**: If the store refuses (state changed after the route's check) → 409 "changed while you were working on it"; a check decided twice → 409 "already decided"
- **Automated**: `test_a_race_lost_in_the_store_is_reported_as_stale`, `test_a_check_decided_twice_is_refused`, `TestInMemoryStore`

### TC-S11: The Supabase store uses atomic RPCs
- **Expected Result**: Send calls `send_event_to_safety_check(p_event_id, p_coordinator_id)`; decisions call `decide_safety_check(p_event_id, p_new_status, p_officer_id, p_notes)` (empty note → NULL); a non-`true` result raises `StaleEventStatus`
- **Automated**: `TestSupabaseStore`

### TC-S12: The page keeps the Coordinator informed
- **Expected Result**: "Checking whether this event is ready…" while loading; the server's sentence when not ready; "Check again" re-fetches; readiness re-checked when the event reloads (after a booking change) and after a refused send; "Waiting for the Safety Officer" once sent
- **Automated**: `SafetyCheckPanel.test.tsx` — "the assigned Coordinator sends a Planning event"

### TC-S13: The Safety Officer's view of an event
- **Expected Result**: Back link goes to "Safety review", not Events; no bookings/equipment cards (their role cannot load them; US17.1); refusals shown in the page's alert
- **Automated**: `EventDetailPage.test.tsx` US4.4 block

---

## 3. NEGATIVE TEST CASES

| ID | Scenario | Expected | Automated |
| --- | --- | --- | --- |
| TC-S20 | A booking still Requested beside a Confirmed one | 409 `venue-not-confirmed`; event unchanged | `test_a_refused_send_names_the_reason_and_changes_nothing` |
| TC-S21 | A live Held booking | `venue-not-confirmed` | `test_a_live_hold_blocks_it` |
| TC-S22 | No active booking (none, or only Cancelled/Rejected/expired) | `no-confirmed-venue` | `test_no_bookings_at_all_is_not_ready`, `test_inactive_bookings_do_not_count_as_a_venue` |
| TC-S23 | Confirmed booking flagged for conflict | `venue-conflict` | `test_a_confirmed_booking_flagged_for_conflict_blocks_it` |
| TC-S24 | Equipment line still Requested | `equipment-not-reserved` | `test_an_equipment_line_still_requested_blocks_it`, `test_readiness_says_what_is_outstanding` |
| TC-S25 | Pending Organiser change request | `change-pending` | `test_a_pending_change_request_blocks_it`, `..._blocks_the_send` |
| TC-S26 | Send from Submitted / Under Review / Approved / Confirmed / Completed | 409 `invalid-transition` | `test_only_planning_moves_to_pending_safety_check` |
| TC-S27 | Send an event already Pending Safety Check | 409 `not-planning` | `test_sending_twice_is_refused` |
| TC-S28 | Another Coordinator's event | 404 (not 403) for readiness and send | `test_another_coordinators_event_is_not_found` |
| TC-S29 | Organiser, Lead, Venue Staff, Safety Officer, Tech Support try to send | 403 "…cannot send events for a safety check" | `test_only_a_coordinator_may_send` |
| TC-S30 | Anyone but the Safety Officer approves / sends back | 403 "…cannot review event safety"; status unchanged | `test_only_the_safety_officer_decides` |
| TC-S31 | Safety Officer approves / sends back a Planning event | 404; unchanged | `test_an_event_not_pending_cannot_be_decided`, `test_planning_no_longer_skips_to_confirmed` |
| TC-S32 | Send back with an empty or blank note | 400; unchanged; button disabled in the UI | `test_sending_back_needs_a_note`; panel "needs a note" |
| TC-S33 | Safety Officer opens a Planning, Confirmed or Draft event, or the events list | 404 / 403 | `test_the_safety_officer_sees_nothing_else`, `test_the_safety_officer_has_no_events_list`; frontend "refuses the Safety Officer an event…" |
| TC-S34 | Queue opened by another role | 403 | `test_the_queue_is_the_safety_officers` |

## 4. BOUNDARY TEST CASES

| ID | Boundary | Expected | Automated |
| --- | --- | --- | --- |
| TC-S40 | Hold expiring exactly now | Counts as expired → ignored (US14.3 rule) | `test_cancelled_rejected_and_expired_bookings_are_ignored` |
| TC-S41 | Note of 2000 / 2001 characters | 200 / 400 | `test_the_note_has_a_limit` |
| TC-S42 | Venue reasons before equipment when both outstanding | `venue-not-confirmed` | `test_venues_are_checked_before_equipment` |

## 5. AC5 / AC6 — the only way into Confirmed

- `transition_allowed(X, Confirmed)` is true only for X = Pending Safety Check (and the
  no-op Confirmed → Confirmed); `transition_allowed(X, Pending Safety Check)` only for
  Planning. Pending Safety Check leaves only for Confirmed or Planning.
  **Automated**: `TestOnlyWayToConfirmed`
- US4.3's transitions are all still allowed, and its full-matrix test
  (`test_every_other_real_transition_is_blocked`) now includes US4.4's three.
- Database backstop: trigger `guard_safety_check_transitions` raises on any status
  write into Confirmed from anything but Pending Safety Check, and into Pending Safety
  Check from anything but Planning — including writes through the generic
  `decide_event_status` RPC.

## 6. Database checks (run manually in the Supabase SQL editor)

Not yet run against the live project. After applying
`SUPABASE_ADD_SAFETY_CHECK_STATUS.sql`, with a Planning test event `:id` assigned to the
Coordinator:

1. `SELECT public.send_event_to_safety_check(:id, :coordinator);` with a Requested booking → `false`, status unchanged.
2. Confirm the booking, remove/reserve equipment, rerun → `true`; one new `status_changes` row.
3. `SELECT public.decide_safety_check(:id, 'Planning', :officer, NULL);` → `false` (note required).
4. `SELECT public.decide_safety_check(:id, 'Confirmed', :coordinator, NULL);` → `false` (not a Safety Officer).
5. `SELECT public.decide_safety_check(:id, 'Confirmed', :officer, NULL);` → `true`; run again → `false`.
6. On another Planning event: `UPDATE public.events SET status = 'Confirmed' WHERE id = :other;` → error "can only become Confirmed from Pending Safety Check".

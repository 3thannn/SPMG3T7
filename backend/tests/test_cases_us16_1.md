# Test Cases for US16.1: Venue Staff Approve or Reject a Booking Request

> As a Venue Staff member, I want to approve or reject venue booking requests,
> so that only bookings we can actually support get confirmed and the
> Coordinator knows where they stand.

## Acceptance Criteria

| # | Criterion |
| --- | --- |
| AC1 | Venue Staff see all Requested bookings, oldest first, showing event name, venue, booking time, the full occupied window including setup/turnaround (US15.1), headcount and layout |
| AC2 | Approve → booking status Confirmed. The conflict check (US15.1) runs again at approval. If the booking now clashes, approval is blocked and the clash is shown, so two requests for the same slot can't both be approved |
| AC3 | Reject → reason required; Venue Staff can optionally suggest an alternative venue or time (free text). Booking status Rejected and the slot is freed |
| AC4 | Approving or rejecting one booking doesn't change the event's other bookings |
| AC5 | The assigned Coordinator is notified of the decision and reason (US10.2) |
| AC6 | Venue Staff only. Decision logged with who/when |

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

### US15.1 placeholder
US15.1 (the conflict check) is not built yet. `backend/app/availability.py` is a
clearly marked **placeholder** holding the smallest version of it, so approval
has a check to run again:

- A booking occupies its venue from start − setup to end + turnaround (US9.4). Back to back is not a clash.
- A slot is **taken** by a **Confirmed** booking, or a **Held** one whose expiry has not passed (US14.3).
- **Requested** bookings do not take it. Two requests for one slot can both wait; whichever is approved first takes it, and that is what blocks the other. If pending requests blocked each other, neither could ever be approved.
- Not yet covered (US15.1 / US12.2): venue unavailability (US12.1 blackouts) and operating hours.

Whoever builds US15.1 should extend `availability.find_clashes` rather than add a second check. The database function `approve_venue_booking` applies the same rule in SQL under a lock on the venue.

### Team assumptions (not customer-confirmed)
- A decision is final: a Confirmed or Rejected booking cannot be decided again or cancelled through US14.2's Cancel.
- Approving or rejecting changes no event status. Moving an event to Confirmed when its bookings are confirmed (US4.5) is not part of this story.
- The reason and suggestion are capped at 2000 characters, like US14.2's cancellation reason.

## Workflow Visualization

```
Coordinator requests a venue (US14.1 / US14.3) ──► booking Requested
                                                        │
Venue Staff ──► "Booking Requests" page: all Requested, oldest first
                event · venue · booking time · occupied window (setup/turnaround)
                headcount · layout · any clash already known
                        │
        ┌───────────────┴───────────────────────────────┐
        ▼ Approve                                        ▼ Reject (reason required,
  find_clashes (US15.1 placeholder)                         suggestion optional)
        │ clash? ──yes──► 409 "already taken… by X"            │
        │                 booking stays Requested               ▼
        ▼ no                                         Rejected, slot freed
  approve_venue_booking (locks venue, re-checks)              │
        │ clash? ──yes──► 409 (lost a race)                    │
        ▼ no                                                   │
  Confirmed (who/when)                                         │
        └──────────────┬───────────────────────────────────────┘
                       ▼
     only this booking's row changes · Coordinator notified (US10.2)
```

## Test Files

| Layer | File |
| --- | --- |
| Backend | `backend/tests/test_booking_decisions.py` (TC-D01–D45) |
| Frontend | `frontend/src/bookingRequestsStore.test.ts` (TC-DF01–DF05), `frontend/src/pages/BookingRequestsPage.test.tsx` (TC-DF06–DF17), `frontend/src/permissions.test.ts` (TC-DF18), `frontend/src/components/TopNav.test.tsx` (TC-DF19), `frontend/src/pages/NotificationsPage.test.tsx` (TC-DF20), `frontend/src/components/EventBookings.test.tsx` (TC-DF21–DF23) |
| Database | Real PostgreSQL; see §6 |
| Updated for US16.1 | `test_venue_booking_cancellation.py` (Confirmed holds a venue, Rejected doesn't); `test_venue_bookings.py` (new `decision` field); `test_venue_holds.py` TC-H41 (a hold cannot be approved straight to Confirmed) |

---

## 1. HAPPY PATH TEST CASES

### TC-D01 / TC-D03: The queue shows what a decision needs (AC1)
- **Pre-conditions**: Great Hall has 30 min setup and 45 min turnaround. Requests 11 (asked 3 Sep), 12 (1 Sep), 13 (2 Sep)
- **Test Steps**: As Venue Staff, `GET /booking-requests`
- **Expected Result**: Order 12, 13, 11 (oldest first). Each shows `eventTitle`, `venueName`, `startsAt`/`endsAt` (09:00–17:00), `occupiedFrom`/`occupiedTo` (08:30–17:45), `setupMinutes` 30, `turnaroundMinutes` 45, `headcount` 120, `requiredLayout` "Theatre", `coordinatorName` "Priya"
- **Automated**: `test_tc_d01_…`, `test_tc_d03_…`; frontend TC-DF06, TC-DF07

### TC-D06: Approving confirms the booking (AC2, AC6)
- **Test Steps**: `POST /booking-requests/11/approve`
- **Expected Result**: HTTP 200; `status` Confirmed; `decision` by Sam with a time and no reason
- **Automated**: `test_tc_d06_…`; frontend TC-DF10

### TC-D19 / TC-D20: Rejecting with a reason, and optionally a suggestion (AC3)
- **Test Data**: `{"reason": "The hall is closed for repairs that week.", "suggestion": "Bertha Room, or the Great Hall on 9 Nov"}`
- **Expected Result**: HTTP 200; `status` Rejected; reason and suggestion recorded with who/when. Without a suggestion it is stored empty
- **Automated**: `test_tc_d19_…`, `test_tc_d20_…`; frontend TC-DF14

### TC-D24: After a rejection the slot can be confirmed for someone else (AC3)
- **Automated**: `test_tc_d24_after_a_rejection_the_slot_can_be_confirmed`

### TC-D28 / TC-D29: The Coordinator is notified (AC5)
- **Expected Result**: Approval → Priya gets `booking-confirmed`: `Venue Staff confirmed Great Hall for "Faculty Welcome Night".` Rejection → `booking-rejected`: `… Reason: Closed that week. Suggested instead: Bertha Room`
- **Automated**: `test_tc_d28_…`, `test_tc_d29_…`, `test_tc_d30_…`, `test_tc_d34_…`; frontend TC-DF20

### TC-D33: The Coordinator sees the decision on the event (AC5)
- **Expected Result**: `GET /events/900/bookings` shows Rejected with the reason, suggestion and Sam
- **Automated**: `test_tc_d33_…`; frontend TC-DF21–DF23

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-D27: Only this booking changes (AC4)
- **Pre-conditions**: Event 900 has requests 11 and 12 and a hold 13
- **Test Steps**: Approve 11; separately, reject 11
- **Expected Result**: Bookings 12 and 13 and the event (still Approved) are exactly as before
- **Automated**: `test_tc_d27_…[approve]`, `[reject]`

### TC-D32: A failed notice doesn't undo the decision (AC5)
- **Automated**: `test_tc_d32_a_failed_notice_does_not_undo_the_decision`

### TC-D15 / TC-D15b / TC-D17 / TC-D26: Two people at once
- **Expected Result**: A clash taken between the check and the write → 409 `slot-taken`; the store re-checks itself; approving or rejecting twice at once → decided once ("already been confirmed/rejected")
- **Automated**: TC-D15, D15b, D17, D26; database concurrency checks in §6

### TC-D41 to TC-D45: The Supabase store
- **Expected Result**: Approve calls `approve_venue_booking`; `clash` and `not-requested` each become their own error; reject writes only a row still Requested, with `suggested_alternative` NULL when empty; the queue reads Requested ordered by `created_at` then `id`
- **Automated**: TC-D41–D45; frontend TC-DF01–DF05

### TC-DF12 / TC-DF16: The page when a decision fails
- **Expected Result**: A refusal is shown on that card and the queue reloads to show the clash as it is now; an unexpected failure says "Could not approve this booking…"
- **Automated**: `BookingRequestsPage.test.tsx`

---

## 3. NEGATIVE TEST CASES

### TC-D07: Two requests for the same slot can't both be approved (AC2)
- **Pre-conditions**: Request 11 (09:00–17:00) and request 12 for another event (12:00–14:00) at Great Hall
- **Test Steps**: Approve 11, then approve 12
- **Expected Result**: 11 Confirmed. 12 → HTTP 409, reason `slot-taken`, message `Great Hall is already taken for this slot by "Faculty Welcome Night" (Confirmed, occupying …)`, `clashes` lists booking 11; 12 stays Requested
- **Automated**: `test_tc_d07_…`; frontend TC-DF11, TC-DF12

### TC-D09 / TC-D12: What takes the slot (AC2)
- **Expected Result**: A confirmed booking ending 08:00 blocks one starting 09:00 (45 min turnaround + 30 min setup overlap); an unexpired hold blocks
- **Automated**: `test_tc_d09_…`, `test_tc_d12_…`

### TC-D16 / TC-D25: Only a Requested booking can be decided
- **Expected Result**: HTTP 409 `not-requested`: "already been confirmed", "already been rejected", "The Coordinator cancelled this booking.", or for a hold "This is a tentative hold. The Coordinator has not requested it yet."
- **Automated**: `test_tc_d16_…`, `test_tc_d25_…`; US14.3's TC-H41

### TC-D21: A reason is required (AC3)
- **Expected Result**: Missing, empty or blank → HTTP 400 "Give the Coordinator a reason for rejecting this booking."; the booking stays Requested
- **Automated**: `test_tc_d21_…`; frontend TC-DF13

### TC-D31: A blocked approval notifies nobody
- **Automated**: `test_tc_d31_a_blocked_approval_notifies_nobody`

### TC-D35 / TC-D36: Venue Staff only (AC6)
- **Expected Result**: Coordinator, Organiser and Coordinator Lead get 403 on the queue, approve and reject, and nothing changes; signed out → 401
- **Automated**: `test_tc_d35_…`, `test_tc_d36_…`; frontend TC-DF18, TC-DF19

### TC-D18: Unknown booking
- **Expected Result**: `999` or `abc` → 404 on approve and reject
- **Automated**: `test_tc_d18_…`

---

## 4. BOUNDARY TEST CASES

Great Hall: 30 min setup, 45 min turnaround. Request 09:00–17:00 occupies 08:30–17:45. "Now" is pinned to 2027-10-01 09:00.

| Case | Other booking | Expected | Automated |
| --- | --- | --- | --- |
| TC-D09 | Confirmed 06:00–08:00 (occupies to 08:45) | Blocked | `test_tc_d09_…` |
| TC-D10 | Confirmed 06:00–07:45 (occupies to 08:30, exactly when this starts) | Approved: back to back | `test_tc_d10_…` |
| TC-D11 | Confirmed, same times, other venue | Approved | `test_tc_d11_…` |
| TC-D12 | Held, expires 8 Oct 17:00, now 1 Oct | Blocked | `test_tc_d12_…` |
| TC-D13 | Held, now exactly its expiry | Approved | `test_tc_d13_…` |
| TC-D08 | Requested, same slot | Approved (requests don't block) | `test_tc_d08_…` |
| TC-D14 | Rejected or Cancelled, same slot | Approved | `test_tc_d14_…` |
| TC-D22 | reason of 2000 characters / 2001 | Accepted / refused (also the suggestion) | `test_tc_d22_…` |
| TC-D05 | empty queue | `[]` | `test_tc_d05_…`; frontend TC-DF08 |
| TC-D05b | event with no Coordinator | `coordinatorName` empty | `test_tc_d05b_…` |
| TC-D38–D40 | the placeholder rule on its own: what takes a slot, no venue = no buffers, unreadable times left out | as stated | `test_tc_d38_…`–`test_tc_d40_…` |

---

## 5. TRACEABILITY MATRIX

| AC | Test cases | Status |
| --- | --- | --- |
| AC1 Queue, oldest first, with every field | TC-D01–D05b, DF06–DF09 | ✅ |
| AC2 Approve → Confirmed, clash check again, blocked and shown | TC-D06–D18, D38–D42, DF10–DF12, DF16; database checks | ✅ using the US15.1 placeholder |
| AC3 Reject → reason, optional suggestion, Rejected, slot freed | TC-D19–D26, D43, D44, DF13–DF15, DF17; database checks | ✅ |
| AC4 Other bookings unchanged | TC-D27 | ✅ |
| AC5 Coordinator notified of decision and reason | TC-D28–D34, DF20–DF23 | ✅ |
| AC6 Venue Staff only; who/when logged | TC-D35–D37, DF18, DF19; database checks | ✅ |

## 6. TEST EXECUTION RESULTS

| Run | Date | Result |
| --- | --- | --- |
| Backend `ruff check`, `compileall`, `pytest` | 2026-10-16 | 1370 passed (57 in `test_booking_decisions.py`) |
| Frontend `lint`, `tsc`, `build`, `vitest` | 2026-10-16 | 779 passed (25 for US16.1) |
| Coverage, `booking_decisions.py`, `availability.py` | 2026-10-16 | 100% |
| Coverage, `BookingRequestsPage.tsx`, `bookingRequestsStore.ts` | 2026-10-16 | 100% of lines |

### Database verification against real PostgreSQL (2026-10-16)
`SUPABASE_ADD_BOOKING_DECISIONS.sql` run on a throwaway PostgreSQL built from
main's `SUPABASE_SETUP.sql` and every migration in README order. 25 of 25 checks passed:

| Check | Result |
| --- | --- |
| Migration applies on top of main's schema, and again (idempotent) | ✅ |
| `booking_status` gains Confirmed and Rejected | ✅ |
| First of two overlapping requests → `confirmed`, with who/when; the second → `clash`, stays Requested | ✅ |
| Approving a Confirmed booking again → `not-requested` | ✅ |
| Turnaround + setup overlap → `clash`; exactly back to back after buffers → `confirmed` | ✅ |
| Same slot at another venue → `confirmed` | ✅ |
| Unexpired hold → `clash`; expired hold → `confirmed` | ✅ |
| Unknown booking → `not-requested` | ✅ |
| A rejection with a blank reason, or a decision without a time, is refused by the table | ✅ |
| A rejected booking frees its slot: the same slot can then be confirmed | ✅ |
| The `booking-confirmed` and `booking-rejected` notice kinds are accepted; unknown kinds still refused | ✅ |
| **Two simultaneous approvals for one slot, from two connections: exactly one wins (5 of 5 runs)** | ✅ |
| Only `service_role` may call `approve_venue_booking` | ✅ |
| The updated `SUPABASE_SETUP.sql` builds a fresh database with the decision columns | ✅ |

**Still to do once the migration is run on Supabase:** a live check against the shared project.

# Test Cases for US15.1 and US15.2: Booking Conflict Detection

> **US15.1** As an Event Coordinator, I want availability checked against the
> full time a venue is occupied, including setup and turnaround, so that I don't
> book a room that's still being prepared or reset.
>
> **US15.2** As the system, I want existing bookings that clash under new
> setup/turnaround times to be flagged, so that clashes get sorted out instead
> of bookings being silently removed.

Week 7 changes #1 (venue setup and turnaround time) and #4 (tentative holds
expire), built on US9.4 (the per-venue minutes), US14.3 (holds), US12.1
(unavailability periods), US16.1 (approval) and US10.2 (Coordinator notices).

## Acceptance Criteria

| # | Criterion |
| --- | --- |
| 15.1-AC1 | Effective occupied window = (start − venue setup time) to (end + venue turnaround time) |
| 15.1-AC2 | Customer's case: event 10:00–12:00, setup 30 min, turnaround 45 min → occupies 9:30–12:45 |
| 15.1-AC3 | Request is blocked if its window overlaps another active booking's window at the same venue. Held, Requested and Confirmed count. Expired, Cancelled and Replaced don't |
| 15.1-AC4 | Also blocked if it overlaps a venue unavailability period (US12.1) |
| 15.1-AC5 | Blocked request says which booking or period it clashes with |
| 15.1-AC6 | Windows that only touch (one ends 12:45, next starts 12:45) are allowed |
| 15.2-AC1 | When a venue's setup or turnaround time changes, all its future active bookings are re-checked with US15.1's rule |
| 15.2-AC2 | Newly clashing bookings are marked 'Conflict – review needed'. Never deleted or cancelled automatically |
| 15.2-AC3 | Venue Staff see a list of flagged bookings; the assigned Coordinator is notified (US10.2) |
| 15.2-AC4 | Flag clears once the clash is resolved (booking moved, cancelled or replaced) |

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

### Where the rule lives
`backend/app/availability.py` replaces the US16.1 placeholder. One rule,
`check_slot`, is used by every route that takes a slot: requesting a venue
(US14.1), the suitability check the form calls as a venue is picked (US18.1),
placing a hold (US14.3), turning a hold into a request (US14.3), approving a
request (US16.1) and US15.2's re-check. `SUPABASE_ADD_BOOKING_CONFLICTS.sql`
applies the same rule in SQL (`venue_slot_clashes`) inside
`request_venue_and_plan` and `approve_venue_booking`, under a lock on the venue.

US15.2 is `backend/app/conflict_flags.py` (flag, clear) and
`backend/app/booking_conflicts.py` (`GET /booking-conflicts`).

### Team assumptions (not customer-confirmed)
- **Approval keeps US16.1's rule for other requests.** A new *request* is blocked by Held, Requested and Confirmed bookings (15.1-AC3). *Approval* is blocked by Confirmed and unexpired Held bookings and by unavailability periods, but not by another Requested booking: two requests can only overlap after a race or a setup/turnaround change, and if they blocked each other neither could ever be approved. Whichever is approved first then blocks the other (US16.1 AC2, TC-D08).
- **The flag is a mark beside the status, not a status.** A flagged booking stays Requested, Held or Confirmed, so clearing the flag needs no guess at what it was before. It is shown as "Conflict – review needed".
- **"Future"** means the booking's occupied window, turnaround included, has not ended yet.
- **An unavailability period covers whole days**, from midnight on its first day to midnight after its last, so setup that reaches back into a closed day clashes, and setup that starts exactly at midnight after one does not.
- **A flag clears** when the booking is cancelled or rejected, its hold expires, the booking it clashed with goes the same way, the minutes change so the windows no longer meet, or the booking finishes. "Moved" and "Replaced" have no route yet (US14.5); they will clear through the same re-check once they exist.
- **Expired holds clear their flag when Venue Staff open the list.** A hold expires without anything being written, so the list re-checks before it reads.
- **Privacy (US8.6):** a Coordinator is told which booking they clash with by number, status and occupied window. The other event's title is named only if it is also theirs. Venue Staff, who see every event, get titles.
- Only a setup/turnaround change flags bookings. A blackout added after bookings exist is US12.2.
- A setup/turnaround save that succeeds is not undone if flagging fails: the failure is logged and the US9.4 re-check still lists the clashes.

## Workflow Visualization

```
US15.1 — a slot is requested (or held, or a hold is requested, or approved)
  window = start − setup … end + turnaround          (half-open: touching is fine)
        │
        ├─ overlaps a Held (unexpired) / Requested* / Confirmed booking at the venue?
        ├─ overlaps an unavailability period (whole days)?
        │        * not counted at approval (US16.1)
        ▼
   yes ─► 409 not-available: "Great Hall is not available for this booking. With setup and
          turnaround it would occupy …, which overlaps booking #11 (Confirmed) occupying …;
          and the venue's unavailable period 2027-11-02 (Maintenance)."  Nothing stored.
   no  ─► stored; request_venue_and_plan re-checks under the venue lock (-1 = taken)

US15.2 — Venue Staff change setup/turnaround (PUT /venues/{id})
        │
        ▼
  every future active booking at the venue re-checked with US15.1's rule
        │
        ├─ clashes, not yet flagged ─► conflict_flagged_at + reason; Coordinator notified
        ├─ clashes, already flagged ─► left as it is (no second notice)
        └─ no longer clashes, flagged ─► flag cleared
        │
        ▼
  GET /booking-conflicts (Venue Staff) ─ clears resolved flags, lists the rest soonest first
  cancel / reject at the venue ─► flags re-checked and cleared where resolved
```

## Test Files

| Layer | File |
| --- | --- |
| Backend | `backend/tests/test_booking_conflicts.py` (TC-C01–C33, TC-F01–F38) |
| Frontend | `frontend/src/components/EventBookings.test.tsx` (TC-CF01–CF07, TC-FF01–FF02), `frontend/src/pages/BookingRequestsPage.test.tsx` (TC-CF08–CF09, TC-FF17), `frontend/src/bookingConflictsStore.test.ts` (TC-CF10–CF11, TC-FF16), `frontend/src/pages/BookingConflictsPage.test.tsx` (TC-FF07–FF15), `frontend/src/pages/VenueFormPage.test.tsx` (TC-FF18–FF21), `frontend/src/components/TopNav.test.tsx` (TC-FF22), `frontend/src/permissions.test.ts` (TC-FF23), `frontend/src/App.test.tsx` (TC-FF24) |
| Database | Real PostgreSQL; see §6 |
| Updated for US15.1/15.2 | `test_lifecycle_us4_5.py` and `test_venue_booking_cancellation.py` (a second booking for the same slot now goes to another venue); `test_venue_holds.py` TC-H24/H25 (a request for a held slot is now refused outright; after expiry it succeeds); `test_venue_bookings.py` (new `conflict` field); `test_venue_suitability.py` (new availability fields); `test_venue_turnaround.py` (bookings are flagged but keep their status; new `flaggedBookingIds`/`clearedBookingIds`) |

---

## 1. HAPPY PATH TEST CASES

### TC-C01: The customer's worked example (15.1-AC1, AC2)
- **Pre-conditions**: Great Hall has 30 min setup and 45 min turnaround
- **Test Steps**: Check 2027-11-02 10:00–12:00 at the Great Hall
- **Expected Result**: Occupied 09:30–12:45; available
- **Automated**: `test_tc_c01_…`, `test_tc_c02b_…` (the window in the API's answer)

### TC-C20 / TC-CF01: The Coordinator sees the window and availability before requesting (15.1-AC1, AC5)
- **Test Steps**: Pick a venue on the event's booking form
- **Expected Result**: "Available: the venue would be occupied 2 Nov 2027, 08:30 – 17:45, setup and turnaround included." Nothing is stored by the check
- **Automated**: `test_tc_c20_…`; frontend TC-CF01, TC-CF04, TC-CF05

### TC-C21 / TC-C23: Back to back after the buffers is allowed (15.1-AC6)
- **Pre-conditions**: Confirmed 10:00–12:00 (occupies to 12:45)
- **Test Steps**: Request 13:15–15:00 (setup from 12:45); separately request 10:00–12:45 before a booking at 14:00 (setup from 13:30, this one's turnaround to 13:30)
- **Expected Result**: HTTP 201 both
- **Automated**: `test_tc_c21_…`, `test_tc_c23_…`

### TC-C26: A clear hold becomes a request (15.1-AC3, US14.3)
- **Automated**: `test_tc_c26_…`

### TC-F01: A change flags both sides of a new clash (15.2-AC1, AC2)
- **Pre-conditions**: Great Hall 0/0. Confirmed 10:00–12:00 and Requested 12:30–14:00, clear of each other
- **Test Steps**: Venue Staff set 30 min setup and 45 min turnaround
- **Expected Result**: HTTP 200; `recheck.flaggedBookingIds` = ["10", "11"]. Booking 10's reason: "With 30 minutes setup and 45 minutes turnaround it occupies 2027-11-02 09:30 to 2027-11-02 12:45, which overlaps booking #11 (Requested) occupying 2027-11-02 12:00 to 2027-11-02 14:45."
- **Automated**: `test_tc_f01_…`; frontend TC-FF18

### TC-F03: The assigned Coordinator of each flagged booking is notified (15.2-AC3)
- **Expected Result**: One `booking-conflict` notice per flagged booking, to that event's Coordinator: 'The booking of Great Hall for "Faculty Welcome Night" needs attention: With 30 minutes setup …'
- **Automated**: `test_tc_f03_…`

### TC-F13 – TC-F18: Venue Staff see the flagged list; the Coordinator sees the flag (15.2-AC3)
- **Test Steps**: `GET /booking-conflicts` as Venue Staff; `GET /events/900/bookings` as the Coordinator; the booking request queue
- **Expected Result**: Flagged bookings soonest first, each with label "Conflict – review needed", reason, event title, Coordinator, occupied window, setup/turnaround, and what it clashes with now (with titles, for Venue Staff). The Coordinator's booking still reads Confirmed, with the flag and reason beside it
- **Automated**: `test_tc_f13_…`–`test_tc_f18_…`; frontend TC-FF01, TC-FF07–FF17

### TC-F19 – TC-F21: The flag clears once the clash is resolved (15.2-AC4)
- **Expected Result**: Cancelling one side (Coordinator) or rejecting it (Venue Staff) clears both flags, and the response shows `conflict: null`; lowering the minutes again lists both in `clearedBookingIds`
- **Automated**: `test_tc_f19_…`, `test_tc_f20_…`, `test_tc_f20b_…`, `test_tc_f21_…`; frontend TC-FF14, TC-FF21

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-F02: Nothing is deleted, cancelled or moved (15.2-AC2)
- **Expected Result**: After the change, every booking has the same id, status, start and end
- **Automated**: `test_tc_f02_…`; `test_venue_turnaround.py::test_problem_bookings_are_identified_not_removed`

### TC-C10 / TC-C10b / TC-C11: Two requests for one slot at once
- **Expected Result**: A slot taken between the route's check and the write → 409 `not-available` naming the winner, or "a booking made a moment ago" if it is gone again; the store re-checks itself (`SlotTaken`); in SQL, two connections → exactly one stored (§6)
- **Automated**: `test_tc_c10_…`, `test_tc_c10b_…`, `test_tc_c11_…`, `test_tc_c32_…`; database race check (§6)

### TC-C10c: A stale event is still its own refusal
- **Automated**: `test_tc_c10c_…`, `test_tc_c33_…`

### TC-F10 – TC-F12 / TC-F27: Notices and flags never undo a saved change
- **Expected Result**: An event that is gone → flagged without a notice; a notice that cannot be written → still flagged; flagging that fails → the venue save still returns 200 with the US9.4 conflicts and the failure is logged; clearing that fails → the cancellation still succeeds and is logged
- **Automated**: `test_tc_f10_…`, `test_tc_f11_…`, `test_tc_f12_…`, `test_tc_f27_…`

### TC-C18 / TC-C19 / TC-F03: Who may read which event's title (US8.6)
- **Expected Result**: A Coordinator's refusal names another Coordinator's booking as "booking #10 (Confirmed) occupying …", never "Board Retreat"; a flag's reason never names the other event; Venue Staff placing a hold see the other event's title
- **Automated**: `test_tc_c18_…`, `test_tc_c19_…`, `test_tc_f03_…`, `test_tc_f17_…`

### TC-F31 – TC-F38: The Supabase and in-memory stores
- **Expected Result**: Every read selects `conflict_flagged_at, conflict_reason`; a row reads its flag or none; flagging writes only those two columns; clearing writes both NULL; a gone booking is stale; the flagged list filters `conflict_flagged_at IS NOT NULL` ordered by `start_at`; the request RPC's -1 is `SlotTaken` and NULL is still a stale event
- **Automated**: TC-F31–F38, TC-C32, TC-C33

---

## 3. NEGATIVE TEST CASES

### TC-C03: Held, Requested and Confirmed block a request (15.1-AC3, AC5)
- **Pre-conditions**: A booking 11:00–13:00 at the Great Hall in each status in turn
- **Test Steps**: Request 10:00–12:00
- **Expected Result**: HTTP 409, `reason` `not-available`, the clash names `(…, Confirmed|Requested|Held) occupying …`; nothing stored
- **Automated**: `test_tc_c03_…[confirmed|requested|held]`; frontend TC-CF02, TC-CF07

### TC-C06: Clashing only once setup and turnaround count (15.1-AC1)
- **Pre-conditions**: Confirmed 08:00–09:00 (occupies 07:30–09:45)
- **Expected Result**: Request 10:00–12:00 (from 09:30) → 409
- **Automated**: `test_tc_c06_…`

### TC-C08: The event's own other booking still counts
- **Automated**: `test_tc_c08_…`

### TC-C12 / TC-C13 / TC-C15: Unavailability periods (15.1-AC4, AC5)
- **Expected Result**: A period on the day → 409 "the venue's unavailable period 2027-11-02 (Maintenance)"; setup at 00:15 reaching into a closed day before → 409; a multi-day period → "2027-11-01 to 2027-11-03 (Closure)"
- **Automated**: `test_tc_c12_…`, `test_tc_c13_…`, `test_tc_c15_…`

### TC-C17: Every clash named, in order (15.1-AC5)
- **Expected Result**: `occupiedFrom`/`occupiedTo` 09:30/12:45; `clashes` lists bookings soonest first, then periods; the message ends "…; and the venue's unavailable period 2027-11-02."
- **Automated**: `test_tc_c17_…`

### TC-C19 / TC-C25: Holds take the same rule (15.1-AC3)
- **Expected Result**: Placing a hold over a Requested booking → 409 (with that event's title, for Venue Staff); a hold that clashes since (a setup change) cannot be turned into a request and stays Held
- **Automated**: `test_tc_c19_…`, `test_tc_c25_…`

### TC-C27 / TC-C28 / TC-C29: Approval is blocked by an unavailability period (15.1-AC4 at approval)
- **Expected Result**: 409 `slot-taken`, "Great Hall is unavailable for this slot: the venue's unavailable period 2027-11-02 (Flooded). Reject this request, or resolve the clash first."; `unavailable` lists the period; with a booking too, both sentences; the store refuses it as well; the queue shows the period and disables Approve
- **Automated**: `test_tc_c27_…`–`test_tc_c29_…`; frontend TC-CF08, TC-CF09

### TC-F04 / TC-F05 / TC-F08: What is not flagged (15.2-AC1)
- **Expected Result**: Cancelled, Rejected and expired-hold bookings, and bookings at other venues, are never flagged; bookings that have finished are not re-checked; a save that changes neither minute value re-checks nothing
- **Automated**: `test_tc_f04_…`, `test_tc_f05_…`, `test_tc_f08_…`

### TC-F07: An already-flagged booking is not flagged or notified again
- **Automated**: `test_tc_f07_…`

### TC-F15 / TC-F16 / TC-FF23: Venue Staff only (15.2-AC3)
- **Expected Result**: Organiser, Coordinator, Coordinator Lead, Safety Officer and Technical Support → 403; signed out → 401; the page and nav link are Venue Staff's only
- **Automated**: `test_tc_f15_…`, `test_tc_f16_…`; frontend TC-FF22–FF24

---

## 4. BOUNDARY TEST CASES

Great Hall: 30 min setup, 45 min turnaround. "Now" is pinned to 2027-10-01 09:00.

| Case | Other booking / period | This slot | Expected | Automated |
| --- | --- | --- | --- | --- |
| TC-C01 | — | 10:00–12:00 | occupies 09:30–12:45 | `test_tc_c01_…` |
| TC-C21 | Confirmed 10:00–12:00 (to 12:45) | 13:15–15:00 (from 12:45) | Allowed: touching | `test_tc_c21_…` |
| TC-C22 | Confirmed 10:00–12:00 (to 12:45) | 13:14–15:00 (from 12:44) | Blocked | `test_tc_c22_…` |
| TC-C23 | Confirmed 14:00–16:00 (from 13:30) | 10:00–12:45 (to 13:30) | Allowed: touching | `test_tc_c23_…` |
| TC-C04 | Held, now exactly its expiry | 10:00–12:00 | Allowed | `test_tc_c04_…` |
| TC-C05 | Cancelled or Rejected, same slot | 10:00–12:00 | Allowed | `test_tc_c05_…` |
| TC-C07 | Confirmed, same times, other venue | 10:00–12:00 | Allowed | `test_tc_c07_…` |
| TC-C14 | Closed 30 Oct – 1 Nov | 2 Nov 00:30 (setup from 00:00) | Allowed: touching midnight | `test_tc_c14_…` |
| TC-C13 | Closed 1 Nov | 2 Nov 00:15 (setup from 23:45) | Blocked | `test_tc_c13_…` |
| TC-C24 | Closed 3 Nov | 2 Nov 22:00 – 3 Nov 00:00 (no venue buffers) | Allowed: touching midnight | `test_tc_c24_…` |
| TC-C16 | Closed that day at another venue | 10:00–12:00 | Allowed | `test_tc_c16_…` |
| TC-C30 | Requested, same slot | approval | Approval allowed (US16.1); a new request blocked | `test_tc_c30_…` |
| TC-C09 / C31 | unreadable times on the other / this booking | — | Left out / clashes with nothing | `test_tc_c09_…`, `test_tc_c31_…` |
| TC-F05 / F24 | booking finished (now 3 Nov) | — | Not flagged / flag dropped | `test_tc_f05_…`, `test_tc_f24_…` |
| TC-F22 | Held side of a flagged pair, now exactly its expiry | list opened | Both flags cleared | `test_tc_f22_…` |
| TC-F28 | 1 minute setup | — | "1 minute setup" (singular) | `test_tc_f28_…`; frontend TC-FF11 |

---

## 5. TRACEABILITY MATRIX

| AC | Test cases | Status |
| --- | --- | --- |
| 15.1-AC1 Occupied window = start − setup to end + turnaround | TC-C01, C02, C02b, C06, CF01; database checks | ✅ |
| 15.1-AC2 Customer's 10:00–12:00 → 09:30–12:45 | TC-C01; database check | ✅ |
| 15.1-AC3 Held/Requested/Confirmed block; Expired/Cancelled don't (Rejected doesn't either) | TC-C03–C11, C19, C25, C26, C30, CF02, CF07; database checks | ✅ ("Replaced" arrives with US14.5) |
| 15.1-AC4 Unavailability period blocks | TC-C12–C16, C24, C27–C29, CF08, CF09; database checks | ✅ |
| 15.1-AC5 Says which booking or period | TC-C03, C12, C15, C17–C20, CF02, CF03, CF07 | ✅ |
| 15.1-AC6 Touching windows allowed | TC-C14, C21–C24; database checks | ✅ |
| 15.2-AC1 Change re-checks future active bookings with US15.1's rule | TC-F01, F04–F06, F08, F09 | ✅ |
| 15.2-AC2 Marked "Conflict – review needed", never deleted or cancelled | TC-F01, F02, F06, F07, F13, F17, FF01, FF18–FF20 | ✅ |
| 15.2-AC3 Venue Staff list; Coordinator notified | TC-F03, F10, F11, F13–F18, FF07–FF17, FF22–FF24 | ✅ |
| 15.2-AC4 Flag clears once resolved | TC-F19–F27, FF14, FF21 | ✅ |

## 6. TEST EXECUTION RESULTS

| Run | Date | Result |
| --- | --- | --- |
| Backend `ruff check`, `compileall`, `pytest` | 2026-10-17 | 1454 passed (84 in `test_booking_conflicts.py`) |
| Frontend `lint`, `tsc`, `build`, `vitest` | 2026-10-17 | 809 passed (31 for US15.1/15.2). 1 failure in `UnassignedQueuePage.test.tsx` that fails the same way on `main` before this change |
| Coverage (line and branch), `availability.py`, `conflict_flags.py`, `booking_conflicts.py`, `booking_decisions.py`, `holds.py`, `venues.py` | 2026-10-17 | 100% |
| Coverage, `events.py` | 2026-10-17 | Every line added for US15.1/15.2 covered; remaining misses are in older event routes |
| Coverage, `BookingConflictsPage.tsx`, `bookingConflictsStore.ts`, `bookingRequestsStore.ts` | 2026-10-17 | 100% lines, branches, functions |
| Coverage, `EventBookings.tsx`, `BookingRequestsPage.tsx`, `VenueFormPage.tsx` | 2026-10-17 | Every line added for US15.1/15.2 covered; remaining misses are in older code |

### Database verification against real PostgreSQL (2026-10-17)
`SUPABASE_ADD_BOOKING_CONFLICTS.sql` run twice on a throwaway PostgreSQL 18
built from main's `SUPABASE_SETUP.sql` and every migration. 30 of 30 checks passed:

| Check | Result |
| --- | --- |
| Migration applies on top of main's schema, and again (idempotent) | ✅ |
| Customer's example: 10:00–12:00 +30/+45; the next setup at 12:45 is back to back; 12:44 clashes | ✅ |
| Ending exactly as another's setup starts is allowed; one minute later clashes | ✅ |
| Same slot at another venue is free | ✅ |
| Requested counts for a new request, not at approval; Cancelled and Rejected never count | ✅ |
| Unexpired hold counts; expired hold does not | ✅ |
| A booking is left out of its own check | ✅ |
| Setup reaching back into a closed day clashes; setup from exactly midnight after one does not; turnaround into the next closed day clashes; another venue's closure does not count | ✅ |
| `request_venue_and_plan`: free slot stored and Approved → Planning; taken slot → -1, nothing stored; stale event → NULL; back to back stored | ✅ |
| `approve_venue_booking`: not blocked by another Requested booking, which it then blocks; blocked by an unavailability period; unknown booking → `not-requested` | ✅ |
| A flag with a reason is stored, status unchanged; a blank reason is refused by the table; clearing nulls both | ✅ |
| Only `service_role` may call `venue_slot_clashes` | ✅ |
| **Two simultaneous requests for one slot, from two connections: exactly one stored (5 of 5 runs)** | ✅ |
| The updated `SUPABASE_SETUP.sql` builds a fresh database with the flag columns, constraint and index | ✅ |

### Not yet run
- Live verification against the shared Supabase project: needs
  `SUPABASE_ADD_BOOKING_CONFLICTS.sql` applied there first.
- A Playwright journey (request → blocked; change setup → flagged → cancel → cleared).

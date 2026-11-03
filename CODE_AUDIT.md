# Code audit: what ConnectSphere actually does

Audited on 2026-11-03 on `chore/playwright-test-reduction-handover` (includes `main`
at `a6c8213`). Everything below was checked by reading the code, running it, or
querying the live database's metadata. Read alongside `REQUIREMENTS_BASELINE.md`.

## 1. Shape of the system

```
React + Vite SPA (frontend/, ~13,900 lines)
   │  HTTPS, bearer token
FastAPI (backend/app/, ~15,700 lines): 10 routers, 81 routes
   │  service-role client
Supabase Postgres: 15 tables (RLS on), 45 functions, 14 triggers
```

- **Two storage implementations.** Every store has a Supabase version (production)
  and an in-memory version (pytest and the isolated browser tests). Business rules
  live in both Python and SQL: Python checks the request, and SQL functions and
  triggers guard the data. A test that runs against the in-memory stores proves
  the Python, not the SQL. Only the four `backend/integration/` modules (run in CI
  against Postgres) prove the SQL.
- **Production matches the repo.** All 21 SQL functions the Python calls are
  deployed, and every function the repo's scripts define is deployed. Two deployed
  functions, `booking_effective_window` and `booking_overlaps_unavailability`,
  appear in no repo script and nothing calls them: leftovers to delete or document.

## 2. Who can do what

78 of the 81 routes require a permission. The other three are `GET /health`,
`POST /auth/login` and `POST /auth/logout`, which is correct.

On top of the role check, the routes that act on one event check the relationship,
mostly through `_readable()` (directly or via a helper) and in a few equipment routes
with an equivalent check. The rule is:
an Organiser sees only their own events, a Coordinator only events assigned to them
(never Drafts), the Lead sees every non-Draft event, and the Safety Officer sees an
event only while it is Pending Safety Check.

| Role | Can |
| --- | --- |
| Organiser | Create, submit, request changes, cancel, read own events and their registrations |
| Coordinator | Review, approve or reject, edit, request bookings and equipment, send to safety check, confirm, complete, cancel, manage registration (assigned events only) |
| Lead | See the unassigned queue and all events, assign and reassign Coordinators, read venues and equipment |
| Venue Staff | Manage venues and unavailability, place holds, approve or reject bookings, see conflicts |
| Technical Support | Manage the equipment catalogue, work the equipment queue, reserve or mark unavailable |
| Safety Officer | Read the safety queue and review, approve, reject or request changes |
| Attendee | See open Confirmed events, register, withdraw, read own registrations |

Two things stand out:

- **The Safety Officer cannot read notifications** (no `NOTIFICATIONS_READ`), and no
  story sends them any. Every other role can.
- **A Coordinator not assigned to an event gets 404 "That event no longer exists."**
  Hiding the event is deliberate, but the wording is wrong, since the event does
  exist. US8.6 asks for "a clear message (US1.3 pattern)".

## 3. The workflow, run end to end

A script drove the in-memory API through one event's whole life (about 40 steps). These
behaved as the stories and the customer say:

| Step | Result |
| --- | --- |
| Draft hidden from Coordinators; submit; Organiser can't edit after submitting | Correct (US2.2, US2.1, Wk4) |
| Lead sees the unassigned queue; Coordinator can't see the event until assigned; assignment moves it to Under Review | Correct (US8.2, US8.6, US8.3, US4.5) |
| Coordinator approves | Approved (US7.1) |
| A venue without the required layout is refused as not suitable | Correct (US18.1) |
| Booking request moves the event to Planning; the same slot again is refused, naming setup and turnaround | Correct (US14.1, US4.5, US15.1) |
| Venue Staff approve; equipment requested and reserved | Correct (US16.1, US19.2, US19.3) |
| Safety check can't start until equipment is reserved | Correct (US4.4) |
| Coordinator can't confirm before Safety approves; Safety approval leaves the event Pending Safety Check | Correct (US4.7, US17.2) |
| Coordinator confirms; direct edits of the Confirmed event are refused | Correct (US4.7, US5.3) |
| Registration at capacity 1: first registers, second gets "Event is full." | Correct (US20.1) |
| An accepted attendance change on the Confirmed event sends it back to Planning | Correct (US11.3) |
| Cancelling releases the venue booking | Correct (US4.6) |

## 4. Defects and deviations found

| # | What happens | Why it matters | Severity |
| --- | --- | --- | --- |
| D1 | After the Safety Officer approves an event for 50 people, the Coordinator can edit attendance to 90 (still within the venue) and then **confirm it**. The Confirmed event rests on a safety approval for different numbers. | Safety must approve before confirmation (Wk7 #6, Wk9), and the review covers attendance. The same change through a change request does invalidate the approval (US11.3); a direct edit during the safety check does not. US5.3 locks only Confirmed events and notes "revisit if Pending Safety Check should lock too". | **Fixed**: an important change now sends the event back to Planning (tests: `test_safety_approval_after_change.py`, `integration/test_safety_check_changes_db.py`; SQL: `SUPABASE_FIX_SAFETY_CHECK_CHANGES.sql`, applied to the live database on 2026-11-03) |
| D2 | A Rejected event cannot be resubmitted ("Only a Draft event can be submitted"). | Three Week 4 customer answers say rejected events may be resubmitted ("Rejected events may be resubmitted after appropriate changes are made; rejection is not necessarily final"). The Week 4 project instructions list Rejected among the statuses but never make it final, so the answer does not contradict them. US4.3's transition list predates the answer. | **Fixed**: the owning Organiser edits a Rejected event and resubmits it (Rejected → Submitted); it returns to the Leads' unassigned queue with its Coordinator cleared (tests: `test_resubmit_rejected_d2.py`, `EventDetailPage.test.tsx`). No SQL change: no database guard covers this move |
| D3 | Only the Coordinator can open or close registration; the Organiser gets 403. | Week 4 answers: "organiser control timing" and "closure is based on Organiser discretion and manually close the registration". The Week 4 instructions say only "where attendee registration is enabled", not by whom, so the answer does not contradict them. | **Fixed**: the owning Organiser may open, close and size registration too; the assigned Coordinator keeps it (tests: `test_registration_us20_1.py::TestWhoMaySetIt`, `integration/test_organiser_registration_db.py`, `EventRegistration.test.tsx`; SQL: `SUPABASE_FIX_ORGANISER_REGISTRATION.sql`) |
| D4 | Unassigned Coordinator sees "That event no longer exists." | Misleading message; US8.6 asks for a clear denial. | **Fixed**: now "That event does not exist, or you do not have access to it." (test: `test_confirm_event_us4_7.py::TestWhoConfirms`) |
| D5 | Two undocumented functions in the live database. | A database rebuilt from the repo would differ from production. Nothing uses them. | Low |
| D6 | The Safety Officer has no notifications. | Not required by any story, but they get no signal when an event is sent for checking. | Low |
| D7 | A booking flagged "Needs replacement" (or a Confirmed one) cannot be cancelled: `cancel` only matches Requested or Held, and the UI hides the button. | US12.2 AC5 says a flagged booking stays flagged "until it is replaced (US14.5) or cancelled (US14.2)", and the Wk4 answer says staff decide offline and the Coordinator records whether to cancel. Week 7 #3 also speaks of "changes or cancellation of one venue arrangement". | **Fixed**: a Confirmed or flagged booking can be cancelled with a reason; a Rejected or Replaced one now says it holds nothing to cancel instead of "already cancelled" (tests: `test_venue_booking_cancellation.py::TestCancellingAConfirmedOrFlaggedBooking`, `EventBookings.test.tsx`). No SQL change: the booking constraints already allow it |
| D8 | After marking a venue unavailable, Venue Staff were told nothing when no bookings were flagged. | US12.2 AC6: "Venue Staff see how many bookings were flagged (including 0)". | **Fixed**: the message now says "No bookings were flagged." (tests: `VenueUnavailability.test.tsx`, E2E `venues-and-bookings.spec.ts`) |

D1 was found by running the code, not by any of the existing tests, all of which
pass. That is the point the course makes about coverage: 100% line coverage did
not catch it.

## 5. What this says about the tests

| | Production lines | Test lines | Tests |
| --- | ---: | ---: | ---: |
| Backend on `main` | 15,700 | 30,000 | 2,513 |
| Backend on this branch | 15,700 | 24,100 | 1,557 |
| Frontend | 13,900 | 18,400 | 1,406 |
| Browser | | | 43 |

The tests are bigger than the code they test, and on `main` about twice its size.

**Sizing by acceptance criteria instead.** The 65 Jira stories carry 284 current AC
items. One happy path plus one or two negative or boundary cases each comes to
roughly **600 to 850 automated tests** across all layers. That also matches the 610-690 target
the team set earlier, now with a reason a reviewer can check.

**Which tests matter most, from this audit:**

1. One end-to-end path through the whole workflow, like section 3. It is the
   strongest evidence that the core features work together, which the Project
   Instructions ask for.
2. Per story: the AC's happy path, its permission refusal, and its rule limits
   (capacity, overlaps, setup and turnaround, statuses).
3. The four `integration/` modules, because they are the only proof the SQL works.
4. A test for each defect in section 4 once it is fixed, starting with D1.

Tests that only re-check what another layer already proves (for example, the same
validation through the store, the route and the React form) are where most of the
excess sits.

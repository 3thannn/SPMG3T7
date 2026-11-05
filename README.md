# SPMG3T7

Monorepo holding both halves of the SPMG3T7 project:

| Directory                | What it is                                   | Stack                                   |
| ------------------------ | -------------------------------------------- | --------------------------------------- |
| [`backend/`](backend/)   | REST API — authentication, roles, events     | Python 3.12, FastAPI, uvicorn, Supabase |
| [`frontend/`](frontend/) | Web client — sign-in, events, backend status | Node 22, React 19, Vite, TypeScript     |

Each directory keeps its own dependencies, tooling and README. There is no shared
build tool at the root — you run each half with its own commands, from its own
directory.

## Prerequisites

- Python 3.12 or newer (`python --version`)
- Node.js 22 or newer and npm 10 (`node --version`)
- Git

## First-time setup

```bash
git clone <this repo>
cd SPMG3T7
```

Backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1     # Windows (PowerShell)
source .venv/bin/activate      # macOS / Linux
pip install -r requirements-dev.txt
```

Then connect it to Supabase, which is where accounts and events live:

```bash
cp .env.example .env      # then fill in the values from your Supabase project
```

The keys go in `backend/.env`, which is gitignored. Only the backend holds them
— the browser talks to the API and never to Supabase directly, so the service
role key never leaves the server.

Passwords are held by Supabase Auth, in the `auth.users` table it manages, and
joined to the project's own `users` row by email.

Frontend:

```bash
cd frontend
npm install
```

### Fresh install: one tested order

For a new Supabase project, apply the scripts in this order. CI builds an empty
PostgreSQL 16 database from exactly this list, twice over to prove each script
is safe to re-run, and then approves and confirms a tentative hold on it
([`backend/integration/test_fresh_install_db.py`](backend/integration/test_fresh_install_db.py)).
The list lives in one place, [`backend/scripts/fresh_install.py`](backend/scripts/fresh_install.py).

1. **Schema.** Either paste each script into the Supabase SQL Editor (Dashboard →
   SQL Editor → New Query → paste → Run), in the order below, or run them all
   with the project's Postgres connection string:

   ```bash
   cd backend
   python scripts/fresh_install.py "postgresql://postgres:<password>@<host>:5432/postgres"
   ```

   1. [`SUPABASE_SETUP.sql`](backend/SUPABASE_SETUP.sql)
   2. [`SUPABASE_ADD_NEW_ROLES.sql`](backend/SUPABASE_ADD_NEW_ROLES.sql)
   3. [`SUPABASE_ALLOW_PARTIAL_DRAFTS.sql`](backend/SUPABASE_ALLOW_PARTIAL_DRAFTS.sql)
   4. [`SUPABASE_CASCADE_STATUS_CHANGES.sql`](backend/SUPABASE_CASCADE_STATUS_CHANGES.sql)
   5. [`SUPABASE_ATOMIC_EVENT_DECISIONS.sql`](backend/SUPABASE_ATOMIC_EVENT_DECISIONS.sql)
   6. [`SUPABASE_ADD_COORDINATOR_ASSIGNMENT.sql`](backend/SUPABASE_ADD_COORDINATOR_ASSIGNMENT.sql)
   7. [`SUPABASE_US5_2_EVENT_CHANGES.sql`](backend/SUPABASE_US5_2_EVENT_CHANGES.sql)
   8. [`SUPABASE_ADD_VENUE_LAYOUTS.sql`](backend/SUPABASE_ADD_VENUE_LAYOUTS.sql)
   9. [`SUPABASE_ADD_VENUE_TURNAROUND.sql`](backend/SUPABASE_ADD_VENUE_TURNAROUND.sql)
   10. [`SUPABASE_ADD_VENUE_UNAVAILABILITY.sql`](backend/SUPABASE_ADD_VENUE_UNAVAILABILITY.sql)
   11. [`SUPABASE_ADD_NOTIFICATIONS.sql`](backend/SUPABASE_ADD_NOTIFICATIONS.sql)
   12. [`SUPABASE_ADD_EQUIPMENT_REQUESTS.sql`](backend/SUPABASE_ADD_EQUIPMENT_REQUESTS.sql)
   13. [`SUPABASE_ADD_COORDINATOR_NOTIFICATIONS.sql`](backend/SUPABASE_ADD_COORDINATOR_NOTIFICATIONS.sql)
   14. [`SUPABASE_ADD_VENUE_BOOKINGS.sql`](backend/SUPABASE_ADD_VENUE_BOOKINGS.sql)
   15. [`SUPABASE_CANCEL_VENUE_BOOKINGS.sql`](backend/SUPABASE_CANCEL_VENUE_BOOKINGS.sql)
   16. [`SUPABASE_ADD_BOOKING_NEEDS.sql`](backend/SUPABASE_ADD_BOOKING_NEEDS.sql)
   17. [`SUPABASE_ADD_CHANGE_REQUESTS.sql`](backend/SUPABASE_ADD_CHANGE_REQUESTS.sql)
   18. [`SUPABASE_US4_5_LIFECYCLE.sql`](backend/SUPABASE_US4_5_LIFECYCLE.sql)
   19. [`SUPABASE_ADD_EVENT_NEEDS.sql`](backend/SUPABASE_ADD_EVENT_NEEDS.sql)
   20. [`SUPABASE_ADD_VENUE_HOLDS.sql`](backend/SUPABASE_ADD_VENUE_HOLDS.sql)
   21. [`SUPABASE_ADD_BOOKING_DECISIONS.sql`](backend/SUPABASE_ADD_BOOKING_DECISIONS.sql)
   22. [`SUPABASE_ADD_BOOKING_CONFLICTS.sql`](backend/SUPABASE_ADD_BOOKING_CONFLICTS.sql)
   23. [`SUPABASE_US14_4_HOLD_EXPIRY.sql`](backend/SUPABASE_US14_4_HOLD_EXPIRY.sql)
   24. [`SUPABASE_US12_2_FLAG_UNAVAILABLE_BOOKINGS.sql`](backend/SUPABASE_US12_2_FLAG_UNAVAILABLE_BOOKINGS.sql)
   25. [`SUPABASE_US14_5_REPLACED_STATUS.sql`](backend/SUPABASE_US14_5_REPLACED_STATUS.sql)
   26. [`SUPABASE_FIX_DECISION_RECORDED.sql`](backend/SUPABASE_FIX_DECISION_RECORDED.sql)
   27. [`SUPABASE_ADD_SAFETY_CHECK_STATUS.sql`](backend/SUPABASE_ADD_SAFETY_CHECK_STATUS.sql)
   28. [`SUPABASE_US4_6_CANCEL_EVENT.sql`](backend/SUPABASE_US4_6_CANCEL_EVENT.sql)
   29. [`SUPABASE_US20_1_REGISTRATION.sql`](backend/SUPABASE_US20_1_REGISTRATION.sql)
   30. [`SUPABASE_US20_2_WITHDRAW.sql`](backend/SUPABASE_US20_2_WITHDRAW.sql)
   31. [`SUPABASE_US4_6_CANCEL_REGISTRATIONS.sql`](backend/SUPABASE_US4_6_CANCEL_REGISTRATIONS.sql)
   32. [`SUPABASE_US17_2_SAFETY_DECISIONS.sql`](backend/SUPABASE_US17_2_SAFETY_DECISIONS.sql)
   33. [`SUPABASE_US19_3_EQUIPMENT_RESERVATIONS.sql`](backend/SUPABASE_US19_3_EQUIPMENT_RESERVATIONS.sql)
   34. [`SUPABASE_US19_EXACT_ITEM_REQUESTS.sql`](backend/SUPABASE_US19_EXACT_ITEM_REQUESTS.sql)
   35. [`SUPABASE_US19_REPAIR_EQUIPMENT_NOTICES.sql`](backend/SUPABASE_US19_REPAIR_EQUIPMENT_NOTICES.sql)
   36. [`SUPABASE_US11_2_CHANGE_REVIEW.sql`](backend/SUPABASE_US11_2_CHANGE_REVIEW.sql)
   37. [`SUPABASE_US11_2_REVIEW_FIXES.sql`](backend/SUPABASE_US11_2_REVIEW_FIXES.sql)
   38. [`SUPABASE_US11_3_RECONFIRM.sql`](backend/SUPABASE_US11_3_RECONFIRM.sql)
   39. [`SUPABASE_US4_7_CONFIRM_EVENT.sql`](backend/SUPABASE_US4_7_CONFIRM_EVENT.sql)
   40. [`SUPABASE_FIX_SAFETY_CHECK_CHANGES.sql`](backend/SUPABASE_FIX_SAFETY_CHECK_CHANGES.sql)
   41. [`SUPABASE_FIX_ORGANISER_REGISTRATION.sql`](backend/SUPABASE_FIX_ORGANISER_REGISTRATION.sql)
   42. [`SUPABASE_US10_4_EVENT_UPDATED_NOTICE.sql`](backend/SUPABASE_US10_4_EVENT_UPDATED_NOTICE.sql)
   43. [`SUPABASE_US8_4_REASSIGN_COORDINATOR.sql`](backend/SUPABASE_US8_4_REASSIGN_COORDINATOR.sql)
   44. [`SUPABASE_US9_5_DELETE_VENUE_HISTORY.sql`](backend/SUPABASE_US9_5_DELETE_VENUE_HISTORY.sql)
   45. [`SUPABASE_US14_5_REQUEST_REPLACEMENT_VENUE.sql`](backend/SUPABASE_US14_5_REQUEST_REPLACEMENT_VENUE.sql)
   46. [`SUPABASE_US12_4_REOPEN_FOR_REPLACEMENT.sql`](backend/SUPABASE_US12_4_REOPEN_FOR_REPLACEMENT.sql)
   47. [`SUPABASE_US12_4_CLOSURE_REOPENS_CONFIRMED.sql`](backend/SUPABASE_US12_4_CLOSURE_REOPENS_CONFIRMED.sql)
   48. [`SUPABASE_US14_6_HOLD_AFTER_APPROVAL.sql`](backend/SUPABASE_US14_6_HOLD_AFTER_APPROVAL.sql)
   49. [`SUPABASE_G13_WEEK1_NOTICES.sql`](backend/SUPABASE_G13_WEEK1_NOTICES.sql)
   50. [`SUPABASE_HARDENING.sql`](backend/SUPABASE_HARDENING.sql)
   51. [`SUPABASE_SEED_VENUES.sql`](backend/SUPABASE_SEED_VENUES.sql)

2. **Scheduler (Supabase only).** Run
   [`SUPABASE_US14_4_SCHEDULE_HOLD_SWEEP.sql`](backend/SUPABASE_US14_4_SCHEDULE_HOLD_SWEEP.sql)
   last. It needs pg_cron, which plain PostgreSQL does not have, so the CI
   build leaves it out.
3. **Accounts.** With `backend/.env` filled in, `python backend/seed_new_users.py`
   creates one account per role (all seven, eight accounts) in Supabase Auth and
   `public.users`. Every account's password is `SEED_PASSWORD` (default
   `password`).
4. Start both halves (below) and sign in as `organiser@connectsphere.com`.

In the SQL Editor, a script that adds an enum value (`ALTER TYPE ... ADD VALUE`,
for example in `SUPABASE_ADD_NEW_ROLES.sql`) must have those lines run on their
own first: Postgres will not use a new value in the transaction that added it.
`fresh_install.py` does this for you.

Do **not** run `SUPABASE_FIX_UNAVAILABILITY_NOTICE.sql` on a new database: it
repaired a live function changed outside the repo, and on a fresh one it would
put back the closure trigger from before US12.4.

### Upgrading an existing project

An existing project only needs the scripts it has not had yet, in the order
above. The table says what each one is for and what breaks without it. All of
them are idempotent, so running one twice is a no-op.

| Script | Needed for | If you skip it |
| ------ | ---------- | -------------- |
| [`SUPABASE_ADD_VENUE_LAYOUTS.sql`](backend/SUPABASE_ADD_VENUE_LAYOUTS.sql) | US9.1a-c, US9.2, US9.3 — every venue route | **All five `/venues` routes return 500.** Reads included, not just writes |
| [`SUPABASE_ADD_VENUE_UNAVAILABILITY.sql`](backend/SUPABASE_ADD_VENUE_UNAVAILABILITY.sql) | US12.1 venue blackout periods | Both `/venues/{id}/unavailability` routes return 500. The other venue routes are unaffected |
| [`SUPABASE_ADD_NOTIFICATIONS.sql`](backend/SUPABASE_ADD_NOTIFICATIONS.sql) | US10.1 Organiser notifications | `/notifications` returns 500 and no notices are written. Event decisions still succeed; the failure is only logged |
| [`SUPABASE_ADD_COORDINATOR_NOTIFICATIONS.sql`](backend/SUPABASE_ADD_COORDINATOR_NOTIFICATIONS.sql) | US10.2 Coordinator notifications. Run after the US10.1 and US19 scripts | Coordinator notices are rejected by the `kind` check, so none are written. Assignment still succeeds; the failure is only logged |
| [`SUPABASE_ADD_VENUE_BOOKINGS.sql`](backend/SUPABASE_ADD_VENUE_BOOKINGS.sql) | US14.1 venue bookings | Every `/events/{id}/bookings` route returns 500, so the bookings card on an event shows an error. `DELETE /venues/{id}` also returns 500, because it checks for bookings first |
| [`SUPABASE_CANCEL_VENUE_BOOKINGS.sql`](backend/SUPABASE_CANCEL_VENUE_BOOKINGS.sql) | US14.2 cancelling a booking. Run after the US14.1 script | Every `/events/{id}/bookings` route returns 500, not only cancel: each booking read selects the cancellation columns. `DELETE /venues/{id}` is unaffected |
| [`SUPABASE_ADD_BOOKING_NEEDS.sql`](backend/SUPABASE_ADD_BOOKING_NEEDS.sql) | US18.1 headcount and needs per booking. Run after the US14.2 script | Every `/events/{id}/bookings` route returns 500: each booking read selects the new columns. The suitability check itself still works, because it reads venues only |
| [`SUPABASE_ALLOW_PARTIAL_DRAFTS.sql`](backend/SUPABASE_ALLOW_PARTIAL_DRAFTS.sql) | US4.2 partial drafts | Saving a draft with no date fails |
| [`SUPABASE_ADD_CHANGE_REQUESTS.sql`](backend/SUPABASE_ADD_CHANGE_REQUESTS.sql) | US11.1 change requests — and every events page | **`GET /events` and every event page return 500**, which the browser reports as a CORS error. See below |
| [`SUPABASE_US4_5_LIFECYCLE.sql`](backend/SUPABASE_US4_5_LIFECYCLE.sql) | US4.5 lifecycle; run after coordinator assignment, venue bookings and needs, and change requests | Assignment, booking, completion and change-request writes require its RPCs and column; event reads also require `request_note` |
| [`SUPABASE_ADD_VENUE_HOLDS.sql`](backend/SUPABASE_ADD_VENUE_HOLDS.sql) | US14.3 tentative holds: the Held status and hold columns. Run after the US14.2, US18.1 and US4.5 scripts. Its hold-first function is dropped by the US14.6 script below | Every `/events/{id}/bookings` route returns 500, because each booking read selects the hold columns; `/holds` returns 500 |
| [`SUPABASE_ADD_BOOKING_DECISIONS.sql`](backend/SUPABASE_ADD_BOOKING_DECISIONS.sql) | US16.1 Venue Staff approve or reject requests. Run after the US14.3, US9.4 and US10.2 scripts | Every `/events/{id}/bookings` route returns 500, because each booking read selects the decision columns; `/booking-requests` returns 500 and nothing can be approved |
| [`SUPABASE_ADD_BOOKING_CONFLICTS.sql`](backend/SUPABASE_ADD_BOOKING_CONFLICTS.sql) | US15.1 conflict check incl. setup/turnaround and unavailability; US15.2 conflict flags. Run after the US16.1, US12.1 and US4.5 scripts | Every `/events/{id}/bookings` route, `/booking-requests`, `/booking-conflicts` and `/holds` return 500, because each booking read selects the flag columns. Two requests for one slot at the same moment could both be stored |
| [`SUPABASE_ADD_SAFETY_CHECK_STATUS.sql`](backend/SUPABASE_ADD_SAFETY_CHECK_STATUS.sql) | US4.4 Pending Safety Check status and transitions. Run after the US4.5, US15.2 and US19 scripts | Sending an event for its safety check and the Safety Officer's decisions return 500; nothing else is affected. Without its trigger, an event could still be moved to Confirmed by a direct status write |
| [`SUPABASE_US4_6_CANCEL_EVENT.sql`](backend/SUPABASE_US4_6_CANCEL_EVENT.sql) | US4.6 cancelling an event. Run after the US4.4, US15.2 and US19 scripts | `POST /events/{id}/cancel` returns 500 (the browser reports "could not reach the API") and nothing changes; every other route is unaffected |
| [`SUPABASE_US14_4_HOLD_EXPIRY.sql`](backend/SUPABASE_US14_4_HOLD_EXPIRY.sql) | US14.4 step 1: the Expired status and the hold sweep. Run after the US14.3, US10.2 and US15.2 scripts | Nothing: it only adds things, and nothing calls the sweep until step 2 |
| [`SUPABASE_US14_4_SCHEDULE_HOLD_SWEEP.sql`](backend/SUPABASE_US14_4_SCHEDULE_HOLD_SWEEP.sql) | US14.4 step 2: pg_cron runs the sweep every 15 minutes. **Run only after US14.4 is merged and everyone has pulled** | Holds still free their slot at the deadline, but are never marked Expired and the Coordinator is never told. Run too early, and older checkouts answer 500 on booking pages |
| [`SUPABASE_US20_1_REGISTRATION.sql`](backend/SUPABASE_US20_1_REGISTRATION.sql) | US20.1 registration: the settings columns, the `registrations` table, the two functions and the `event-full` notice kind. Run after the US4.4 and US16.1 scripts | The registration card on an event and the Attendee's Upcoming Events page return 500; every other route is unaffected |
| [`SUPABASE_US20_2_WITHDRAW.sql`](backend/SUPABASE_US20_2_WITHDRAW.sql) | US20.2 withdrawing: the Withdrawn status, `withdrawn_at` and `withdraw_registration`. Run after the US20.1 script | My Registrations and withdrawing return 500; registering and every other route are unaffected |
| [`SUPABASE_US4_6_CANCEL_REGISTRATIONS.sql`](backend/SUPABASE_US4_6_CANCEL_REGISTRATIONS.sql) | US4.6 with registrations: cancelling marks them Event Cancelled and closes registration. Run after the US4.6 and US20.2 scripts | Cancelling still works, but registrations stay Registered on the cancelled event and registered Attendees are not told |
| [`SUPABASE_US9_5_DELETE_VENUE_HISTORY.sql`](backend/SUPABASE_US9_5_DELETE_VENUE_HISTORY.sql) | US9.5: deleting a venue with no future bookings deletes its past and closed bookings with it, and the database refuses the delete while one is still to come. Run after the US14.3 and US12.2 scripts | Venues with only past or closed bookings still cannot be deleted: the API answers 500 when it tries |
| [`SUPABASE_FIX_DECISION_RECORDED.sql`](backend/SUPABASE_FIX_DECISION_RECORDED.sql) | US4.6 alongside US12.2 and US14.5: one definition of `venue_bookings_decision_recorded` with every story's exception. Run after the US12.2 and US14.5 scripts | **Cancelling an event with a Confirmed booking returns 500**: the US12.2 script redefined the constraint without US4.6's exception for cancelled bookings |
| [`SUPABASE_FIX_UNAVAILABILITY_NOTICE.sql`](backend/SUPABASE_FIX_UNAVAILABILITY_NOTICE.sql) | US12.2: puts back the committed `flag_bookings_for_unavailability()`, whose notice must carry no status. Only needed where the live function was changed outside the repo | **Marking a venue unavailable over an existing booking returns 500** (the browser says CORS): the notice violates `notifications_kind_valid` |
| [`SUPABASE_US11_3_RECONFIRM.sql`](backend/SUPABASE_US11_3_RECONFIRM.sql) | US11.3: approving an important change to a Confirmed event sends it back to Planning (`us11_approve_change`), the guard on where a Confirmed event may go, and the `back-in-planning` notice kind. Run after the US11.2 and US4.4 scripts | **Approving any change request returns 500**; rejecting, proposing and every other route are unaffected |
| [`SUPABASE_US4_7_CONFIRM_EVENT.sql`](backend/SUPABASE_US4_7_CONFIRM_EVENT.sql) | US4.7: the Coordinator confirms the event (`confirm_event`), a safety approval no longer confirms it, the guard that makes confirming the only way into Confirmed, and the `safety-approved` notice kind. Run after the US17.2, US11.2 and US11.3 scripts | **Confirming returns 500**, and a safety approval still confirms the event on its own, as before US4.7 |
| [`SUPABASE_FIX_SAFETY_CHECK_CHANGES.sql`](backend/SUPABASE_FIX_SAFETY_CHECK_CHANGES.sql) | An important change (date, time, attendance, venue or equipment) to an event Pending Safety Check sends it back to Planning, through a Coordinator's edit (`us11_edit`, which gains an optional `p_reason`) or an accepted change request (`us11_approve_change`), so an earlier safety approval cannot confirm it. Run after the US11.2, US11.3 and US4.7 scripts, and before deploying the backend that sends `p_reason` | **Coordinator edits return 500** once the new backend is deployed; before that, an important change during the safety check keeps the old approval |
| [`SUPABASE_FIX_ORGANISER_REGISTRATION.sql`](backend/SUPABASE_FIX_ORGANISER_REGISTRATION.sql) | D3 (applied live 2026-11-03): the owning Organiser may open and close registration and set its capacity, as well as the assigned Coordinator (`set_event_registration`). Run after the US20.1 script | An Organiser's registration save is refused (409, "changed while you were working on it"); the Coordinator's still works |
| [`SUPABASE_US14_5_REQUEST_REPLACEMENT_VENUE.sql`](backend/SUPABASE_US14_5_REQUEST_REPLACEMENT_VENUE.sql) | US14.5: `request_replacement_venue`, which used to exist only on the live database. Created only where it is missing, so the live version is kept. Run after the US14.5 status and US15.2 scripts | **A fresh database cannot request a replacement venue** (500) |
| [`SUPABASE_US12_4_REOPEN_FOR_REPLACEMENT.sql`](backend/SUPABASE_US12_4_REOPEN_FOR_REPLACEMENT.sql) | US12.4: `us12_4_request_replacement` requests the replacement through `request_replacement_venue` and moves an event still Confirmed back to Planning in the same transaction. Run after the US12.2 (or its fix), US14.5 and US11.3 scripts | **Requesting a replacement venue returns 500**; searching for one and every other route are unaffected |
| [`SUPABASE_US12_4_CLOSURE_REOPENS_CONFIRMED.sql`](backend/SUPABASE_US12_4_CLOSURE_REOPENS_CONFIRMED.sql) | US12.4 as Week 9 settled it (G12): a venue closure sends a Confirmed event back to Planning at once, with the reason in its history, and tells the Coordinator and the Organiser. Also compares a hold's expiry in Singapore time. Run after the script above | A closure flags the booking but leaves the event showing Confirmed with a venue it cannot use |
| [`SUPABASE_US14_6_HOLD_AFTER_APPROVAL.sql`](backend/SUPABASE_US14_6_HOLD_AFTER_APPROVAL.sql) | US14.3 reworked and US14.6 (Week 9): Venue Staff approve a request as a hold (`approve_venue_booking_as_hold`), the Coordinator confirms it (`confirm_held_booking`), and the hold notice kinds. Drops the old hold-first `request_held_booking`. Run after the US14.4, decision-recorded fix and US10.4 scripts | **Approving as a hold and confirming a hold return 500**; approving outright still works |
| [`SUPABASE_G13_WEEK1_NOTICES.sql`](backend/SUPABASE_G13_WEEK1_NOTICES.sql) | G13: the notice kinds for a booking requested, registration opened or closed, and an Attendee withdrawing. Run after the US10.4 script | Those notices are rejected and only logged; the actions themselves succeed |
| [`SUPABASE_US10_4_EVENT_UPDATED_NOTICE.sql`](backend/SUPABASE_US10_4_EVENT_UPDATED_NOTICE.sql) | US10.4: the `event-updated` notice kind, which tells registered Attendees their event has a new date, time or venue. Run after the US4.7 script | Attendees' notices are rejected by the `kind` check, so none are written. Approving the change or the replacement venue still succeeds; the failure is only logged |
| [`SUPABASE_US8_4_REASSIGN_COORDINATOR.sql`](backend/SUPABASE_US8_4_REASSIGN_COORDINATOR.sql) | US8.4: `reassign_event_coordinator`, which moves an assigned, active event to another Coordinator, logs it naming the previous one and notifies both. First created on the live database by an uncommitted repair script; this is that function with two US8.4 changes (finished events refused, names in the log). Run after the US10.2 and US12.2 scripts | **A fresh database cannot reassign** (the API answers 409). On the live database, the repair script's version stays: finished events can be reassigned and the log gives ids |
| [`SUPABASE_US17_2_SAFETY_DECISIONS.sql`](backend/SUPABASE_US17_2_SAFETY_DECISIONS.sql) | US17.2 Safety Officer decisions: the `safety_reviews` and `safety_review_flags` tables, `record_safety_decision`, the re-review check in `send_event_to_safety_check`, and the `safety-rejected` notice kind. Run after the US4.4 and US20.1 scripts | Recording a safety decision, listing an event's decisions, resolving a flag and checking safety-check readiness return 500; every other route is unaffected |
| [`SUPABASE_ADD_EVENT_NEEDS.sql`](backend/SUPABASE_ADD_EVENT_NEEDS.sql) | US2.1 (Sprint 3) mandatory event needs; run after the US4.5 script | **`GET /events` and every event page return 500**: each event read selects the new columns |
| [`SUPABASE_ADD_VENUE_TURNAROUND.sql`](backend/SUPABASE_ADD_VENUE_TURNAROUND.sql) | US9.4 venue setup and turnaround time; run after the US14.1 script | **All five `/venues` routes return 500**: each venue read selects the new columns |
| [`SUPABASE_HARDENING.sql`](backend/SUPABASE_HARDENING.sql) | Row Level Security, indexes | Supabase advisor warnings; the app still works |
| [`SUPABASE_SEED_VENUES.sql`](backend/SUPABASE_SEED_VENUES.sql) | Optional | The catalogue shows its empty state until Venue Staff add records |

#### Known issue: venue routes fail with HTTP 500

**Symptom.** Any venue page shows an error; adding a venue reports *"Could not
save this venue."* The backend log carries:

```
postgrest.exceptions.APIError: {'message': "Could not find the
'supported_layouts' column of 'venues' in the schema cache", 'code': 'PGRST204'}
```

**Cause.** US9.1a lists supported layouts as a venue field and the original
schema had no column for it. Every venue route selects `supported_layouts`, and
`POST`/`PUT` send it, so a database without the column fails on the first venue
request — which is why reads break too, not only writes.

**Fix.** Run the one statement in
[`SUPABASE_ADD_VENUE_LAYOUTS.sql`](backend/SUPABASE_ADD_VENUE_LAYOUTS.sql):

```sql
ALTER TABLE public.venues ADD COLUMN IF NOT EXISTS supported_layouts TEXT;
```

No restart is needed — PostgREST picks the column up on its own, and the next
request succeeds. This cannot be applied from the app: the backend goes through
PostgREST, which does not run DDL.

### Development accounts

Nothing in the app creates an account (there is no self-registration, as the
customer asked). `python backend/seed_new_users.py` makes one per role. Each
needs **two** records joined on email: an Auth user holding the password and a
`public.users` row holding the name and role; the script writes both, and the
dashboard (Authentication → Users → Add user, with **Auto Confirm User** on)
works too. One person holds one role; a person with two roles uses two accounts
(see REQUIREMENTS_BASELINE.md, G6).

| Email | Role | Can |
| ----- | ---- | --- |
| `organiser@connectsphere.com` | Event Organiser | create, read own and submit events |
| `coordinator@connectsphere.com` | Event Coordinator | review and edit assigned events, read the venue catalogue |
| `coordinatorlead@connectsphere.com` | Event Coordinator Lead | assign and reassign events, see all events (US8.2-8.5) |
| `venuestaff@connectsphere.com` | Venue Staff | manage the venue catalogue and approve booking requests |
| `safetyofficer@connectsphere.com` | Safety Officer | review events for safety compliance (US17.1-17.2) |
| `technicalsupport@connectsphere.com` | Technical Support Staff | manage equipment catalogue and reservations (US19) |
| `attendee@connectsphere.com`, `attendee2@connectsphere.com` | Attendee | see Confirmed events taking registrations and register (US20.1) |

The role strings are `user_role` enum values, so Postgres rejects a typo rather
than creating a user nobody has permissions for. These are development
credentials, not secrets, and must not survive into a deployed environment.


## Run both halves

The frontend calls the backend, so start the API first. Use two terminals.

Terminal 1 — API on <http://localhost:8000>:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Terminal 2 — client on <http://localhost:5173>:

```bash
cd frontend
npm run dev
```

Open <http://localhost:5173>. The page reports **Backend connected** when it can
reach `/health`, and **Backend unreachable** when it cannot — the latter is the
expected state if you skipped terminal 1, not a build failure.

Sign in with one of the development accounts, both with the password
`password`:

| Email                     | Role              | Can do                                |
| ------------------------- | ----------------- | ------------------------------------- |
| `organiser@connectsphere.com`   | Event Organiser   | create, edit and submit their events  |
| `coordinator@connectsphere.com` | Event Coordinator | see assigned events, review them     |
| `coordinatorlead@connectsphere.com` | Event Coordinator Lead | assign events, see all events |

The role names come from the `user_role` enum in the database, which is why they
read as `Event Organiser` rather than `Organiser`.

These are development credentials, not secrets, and they must not survive into a
deployed environment. Nothing in the app creates an account, so they exist only
once someone has made them by hand in the Supabase dashboard — [the backend
README](backend/README.md#development-accounts) says how. Signing in needs the
API running — there is no way past the form without it.

## Run the checks

These are exactly what CI runs, so green here means green there.

```bash
cd backend  && ruff check . && python -m compileall -q app && pytest --cov
cd frontend && npm run lint && npm run build && npm test -- --coverage
```

## Test coverage

Both halves measure coverage in CI, and the build fails if it drops below the
floor. Measured on 4 November 2026, on the branch that closed the audit gaps:

| Half | Lines | Branches | Statements / functions | Floor, enforced by |
| ---- | ----- | -------- | ---------------------- | ------------------ |
| Backend (`app/`, 791 tests) | 88.82% (5139 of 5786) | 74.77% (984 of 1316) | — | 85.6% lines and branches combined (86.22% now), `fail_under` in [`backend/pyproject.toml`](backend/pyproject.toml) |
| Frontend (`src/`, 76 tests) | 53.34% | 49.73% | 51.82% / 50% | lines 52, statements 51, functions 49, branches 48, `thresholds` in [`frontend/vite.config.ts`](frontend/vite.config.ts) |

Neither half is at 100%, and this README used to say both were. The floors were
lowered when the suite was cut back to one test per acceptance criterion plus
its negative and boundary cases (PR #64), which the rubric's "test cases from
the acceptance criteria" asks for first. What is not covered is mostly:

* **Backend:** the `Supabase*` store classes' error paths (a PostgREST failure,
  a row that vanished between two reads), which need a real database to reach,
  and validation branches in `events.py`, `equipment.py` and `venues.py` whose
  rule is already covered from another route. The SQL itself is tested against
  PostgreSQL in CI (below).
* **Frontend:** loading and error states, and pages whose behaviour is tested
  end to end by the Playwright journeys instead. Browser journeys do not count
  towards these figures.

These could be covered; they are not impossible to reach. They are left as the
known gap, and listed here so the figures are not mistaken for 100%.

### What is excluded, and why

Each exclusion is marked in the code with the reason beside it.

| Where | What | Why it cannot run |
| ----- | ---- | ----------------- |
| `frontend/src/main.tsx` | The whole file | It only mounts `<App />` into the page. |
| `frontend/src/test/` | The whole folder | Test helpers, not product code. |
| `backend/app/events.py`, `save_event` | "Coordinators can only edit submitted events" | `_readable` already answers 404 to anyone but the owner for a draft. Kept so the rule survives a change to who can read one. |
| `frontend/src/components/EventBookings.tsx` | Blank cancellation reason; no replacement venue chosen | Each button is disabled until the field is filled. |
| `frontend/src/pages/EventDetailPage.tsx` | Blank clarification request; blank rejection reason | Each button is disabled until the text is typed. |
| `frontend/src/components/EquipmentReservation.tsx` | Deciding while busy; reserving without stock | Both buttons are disabled in exactly those states. |
| `frontend/src/App.tsx` | `if (!session)` before the signed-in routes | Narrows the type only: every route without a session has already returned. |

### What coverage does not measure

Coverage counts the Python and TypeScript. It does not count the SQL functions
in `backend/SUPABASE_*.sql`, and several rules live there: approving a booking
under a lock on the venue, the conflict check, registering for a place,
recording a safety decision. Those are tested against a real database by
`backend/integration/`, which CI runs against a disposable PostgreSQL 16 (the
"Test database migrations" step), including the fresh-install build. The same
step runs the hold sweep (TC-US14.4-02) and the equipment race (TC-US19.3-08)
from `backend/tests/`, each on a new database built by
`scripts/fresh_install.py`. Locally they skip unless `TEST_POSTGRES_DSN` points
at a disposable server.

### Dates in the tests

Fixture events are dated in late 2026. To stop them being refused as "in the
past" once those days go by, the backend suite pins today to 1 October 2026
(`TODAY` and `pinned_today` in `backend/tests/conftest.py`). The frontend tests
that submit events pin `Date` the same way.

## How the two halves connect

The frontend reads `VITE_API_BASE_URL` (default `http://localhost:8000`) to find
the API; the backend reads `CORS_ORIGINS` (default `http://localhost:5173`) to
decide who may call it. The defaults line up, so local development needs no
configuration. Change one and you must change the other.

| Variable                    | Side     | Default                 | Purpose                                    |
| --------------------------- | -------- | ----------------------- | ------------------------------------------ |
| `VITE_API_BASE_URL`         | frontend | `http://localhost:8000` | Base URL of the backend API                |
| `CORS_ORIGINS`              | backend  | `http://localhost:5173` | Comma-separated origins allowed to call it |
| `SESSION_IDLE_MINUTES`      | backend  | `30`                    | Inactivity after which a session expires   |
| `SUPABASE_URL`              | backend  | *required*              | Supabase project URL                       |
| `SUPABASE_ANON_KEY`         | backend  | *required*              | Anon key, subject to Row Level Security    |
| `SUPABASE_SERVICE_ROLE_KEY` | backend  | *required*              | Service role key — full admin, backend only |
| `SUPABASE_DB_URL`           | backend  | unset                   | Postgres connection string; optional        |

The Supabase values are backend-only and deliberately have no `VITE_` twin: only
`VITE_`-prefixed variables reach the browser, and none of these should. Never put
a secret behind that prefix.

Copy [`frontend/.env.example`](frontend/.env.example) to `frontend/.env.local` to
override the frontend value, and [`backend/.env.example`](backend/.env.example)
to `backend/.env` for the rest.

## Continuous integration

One workflow, [`.github/workflows/ci.yml`](.github/workflows/ci.yml), with three
jobs, all run on every push to `main` and on every pull request. A failing step
fails the build and blocks the PR.

* `CI / backend`: lint, byte-compile, the unit and API tests with coverage, then
  the database tests and the fresh-install build against PostgreSQL 16.
* `CI / frontend`: lint, type-check and build, then the component tests with
  coverage.
* `CI / e2e`: the Playwright browser journeys, against the real API over
  in-memory stores (desktop Chromium).

The jobs run in parallel, so a full run takes as long as the slowest rather
than the sum.

There are deliberately no `paths:` filters. The two halves are not independent —
the client calls the API, so a change to one can break the other — and a check
that only sometimes runs cannot safely be marked as a *required* status check: a
pull request that misses the filter would wait forever for a check that never
starts. Running both every time costs a couple of runner-minutes and means a
missing check is always a real problem rather than something to work out.

## Repository layout

```
backend/
  app/
    main.py            FastAPI application and routes
    config.py          environment-driven settings
    auth.py            /auth routes and the dependencies that guard a route
    permissions.py     roles, permissions, and which role holds what
    users.py           the user directory, over the Supabase users table
    sessions.py        session store with a sliding inactivity window
    security.py        session-token generation
    supabase_client.py the Supabase clients, and which key each one uses
    events.py          /events routes — US4.1, US4.2, and US14.1's venue bookings
    event_store.py     event data access, over events and status_changes and event_change_requests
    booking_store.py   venue booking data access, over venue_bookings
    suitability.py     whether a venue suits one booking (US18.1)
    event_status.py    the status label set, the submit rule and the US7.3 review rule
    change_requests.py the US11.1 rules: which fields changed, which are
                       important, and when a change may be requested
    venues.py          /venues routes — US9.1a-c, US9.2 and US9.3
    venue_store.py     venue data access, over the venues table
  tests/               one file per story, plus unit tests for each module
  pyproject.toml       ruff and pytest configuration
  requirements.txt     runtime dependencies
  requirements-dev.txt runtime + test/lint tooling (what CI installs)
frontend/
  src/
    main.tsx           React entry point
    App.tsx            root component: session, route guards, health status
    router.ts          hash router — five routes, no routing dependency
    api.ts             backend client and its error types
    session.ts         the stored session, revived on load
    permissions.ts     which route needs which permission
    useIdleSignOut.ts  signs out after the server's idle window
    eventsStore.ts     the /events client
    venuesStore.ts     the /venues client, and the venue form rules
    status.ts          event status model and roles
    pages/             sign-in, landing, events, event detail, venues, venue
                       detail, venue form, access denied
    components/        top nav, status badge, status timeline, venue
                       unavailability, event venue bookings
  index.html
  package.json
  vite.config.ts
.github/workflows/     ci.yml — one job per half
```

## History

This repo was formed by combining two previously separate repositories,
`SPMG3T7BackEnd` and `SPMG3T7FrontEnd`. Both histories are preserved — commits
made before the merge appear under their original messages and authors, with
their paths rewritten under `backend/` and `frontend/`. `git log --follow` on any
file works back through the merge.

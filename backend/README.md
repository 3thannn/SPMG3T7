# SPMG3T7 — Backend

FastAPI service for the SPMG3T7 project. The client lives alongside it in this
same repo, under [`../frontend/`](../frontend/); see the
[root README](../README.md) for how to run both halves together.

## Prerequisites

- Python 3.12 or newer (`python --version`)
- Git

## Local setup

All commands below are run from this `backend/` directory.

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements-dev.txt
```

`requirements.txt` holds runtime dependencies only; `requirements-dev.txt` includes
those plus the test and lint tooling, and is what CI installs.

## Connect to Supabase

Accounts and events live in Supabase (Postgres). The backend is the only thing
that holds the credentials — the browser talks to this API and never to Supabase
directly, so the service role key stays on the server.

Copy [`.env.example`](.env.example) to `.env` and fill it in from your Supabase
project. `.env` is gitignored; the keys in it are secrets and must not be
committed.

| Variable                    | Where to find it                                  |
| --------------------------- | ------------------------------------------------- |
| `SUPABASE_URL`              | Project Settings → Data API → Project URL         |
| `SUPABASE_ANON_KEY`         | Project Settings → API Keys → `anon` / public     |
| `SUPABASE_SERVICE_ROLE_KEY` | Project Settings → API Keys → `service_role`      |
| `SUPABASE_DB_URL`           | Connect → Session pooler (optional; see below)    |

`SUPABASE_DB_URL` is unused by the API, which goes through PostgREST. It is
required when running the US19 migration script below or inspecting the schema
directly. Use the **Session pooler** string rather than the direct connection,
which is IPv6-only and fails on most home networks.

For a new project, run [`SUPABASE_SETUP.sql`](SUPABASE_SETUP.sql) once. For the
already-created project, run [`SUPABASE_HARDENING.sql`](SUPABASE_HARDENING.sql)
once in the Supabase SQL Editor. It adds the missing audit foreign-key index,
locks the timestamp trigger's search path, and makes the server-only Data API
access model explicit; it does not alter existing rows or table shapes.

To allow a Draft with no start date, existing projects must also run
[`SUPABASE_ALLOW_PARTIAL_DRAFTS.sql`](SUPABASE_ALLOW_PARTIAL_DRAFTS.sql) once.
It only drops the `NOT NULL` constraint from `events.proposed_date`; completed
event requests and submitted drafts still require a date in application
validation.

## Run the API

```bash
uvicorn app.main:app --reload --port 8000
```

- API root: <http://localhost:8000>
- Health check: <http://localhost:8000/health> → `{"status": "ok"}`
- Interactive docs: <http://localhost:8000/docs>

## Authentication

Sign in with `POST /auth/login` and you get back an opaque session token plus
who you are, what your role may do, and where your role lands in the client.
Send it as `Authorization: Bearer <token>` on every other route.

### Where a password lives

Not in this project's schema. A person is two records, joined on email:

| Record          | Answers                        | Owned by     |
| --------------- | ------------------------------ | ------------ |
| `auth.users`    | can they prove who they are?   | Supabase Auth |
| `public.users`  | who are they, and what may they do? | this project |

`POST /auth/login` hands the email and password to Supabase Auth. If Auth says
yes, the `users` row is looked up by email to find the name and role, and this
API issues its own session token. Nothing about the credential is stored in, or
read from, the `users` table — which is why the schema needed no new column.

Either half can be missing, and both are refused the same way as a wrong
password: an Auth account with no profile row has no role we could put on a
session, and a profile row with no Auth account has nothing to prove itself
with.

The session token stays this project's own rather than passing Supabase's JWT
through to the browser. A JWT is valid until it expires and cannot be taken
back, and US1.2 asks for a sign-out that ends the session *now* — see below.

| Route              | Who                | Purpose                                          |
| ------------------ | ------------------ | ------------------------------------------------ |
| `POST /auth/login` | anyone             | Exchange credentials for a session (US1.1)       |
| `POST /auth/logout`| anyone             | End the session immediately (US1.2)              |
| `GET /auth/me`     | any signed-in user | Who this token belongs to; used to restore a session |
| `GET /auth/users`  | Coordinator only   | The user directory — the first route behind the permission layer (US1.3) |

A session slides: every authenticated request extends it, so it survives normal
use and lapses only after `SESSION_IDLE_MINUTES` without one. Sessions are held
in memory, so restarting the API signs everyone out. Accounts and events are in
Supabase and survive a restart; only the sessions do not, which is the tradeoff
for being able to revoke one the instant someone signs out.

## Events

The routes behind US4.1 and US4.2. This is their enforcement point: the client
mirrors the rules so it can disable a button and explain why, but a disabled
button is a courtesy and a refused request is the rule.

| Route                        | Who                           | Purpose                                    |
| ---------------------------- | ----------------------------- | ------------------------------------------ |
| `GET /events`                | Organiser (own), Coordinator (assigned) | The events list (US4.1/US8.1)     |
| `GET /events/{id}`           | as above                      | One event, with its audit trail            |
| `POST /events`               | Organiser                     | Create — always lands in Draft (US4.2)     |
| `PUT /events/{id}`           | the owning Organiser (Draft only); assigned Coordinator | Save edits; the status does not move |
| `POST /events/{id}/submit`   | the owning Organiser          | Draft → Submitted, once (US4.2)            |
| `POST /events/{id}/clarification` | assigned Coordinator     | Ask for info or changes; → Under Review (US7.3) |
| `POST /events/{id}/approve`  | assigned Coordinator        | Under Review → Approved (US7.1)       |
| `POST /events/{id}/reject`   | assigned Coordinator        | Under Review → Rejected with a reason (US7.1) |
| `POST /events/{id}/change-request` | the owning Organiser  | Propose changes to a submitted event; → Under Review (US11.1) |
| `POST /events/{id}/change-request/approve` | assigned Coordinator | Apply the proposed changes (US11.1) |
| `POST /events/{id}/change-request/reject` | assigned Coordinator | Keep the current details, with a reason (US11.1) |
| `GET /events/{id}/bookings`  | owning Organiser, assigned Coordinator | The event's venue bookings, soonest first (US14.1) |
| `POST /events/{id}/bookings` | assigned Coordinator        | Request one venue; it starts Requested (US14.1) |
| `POST /events/{id}/bookings/{bookingId}/cancel` | assigned Coordinator | Cancel one booking with a reason (US14.2) |
| `POST /events/{id}/bookings/suitability` | assigned Coordinator | Whether a venue suits a booking; stores nothing (US18.1) |
| `GET /events/{id}/safety-check` | assigned Coordinator | Whether the event is ready for its safety check, and if not why (US4.4) |
| `POST /events/{id}/safety-check` | assigned Coordinator | Planning → Pending Safety Check, once ready (US4.4) |
| `GET /events/safety-check` | Safety Officer | Events Pending Safety Check, oldest first (US4.4/US17.1) |
| `GET /events/{id}/safety-review` | Safety Officer | Read-only review of a waiting event: attendance, venues, restrictions, reserved equipment (US17.1) |
| `POST /events/{id}/safety-check/approve` | Safety Officer | Pending Safety Check → Confirmed (US4.4) |
| `POST /events/{id}/safety-check/return` | Safety Officer | Pending Safety Check → Planning, with a note (US4.4) |
| `POST /events/{id}/cancel` | the owning Organiser, assigned Coordinator | Cancel with a reason; releases bookings, holds and equipment (US4.6) |

An event that belongs to another Organiser answers `404`, not `403`. Telling
someone an event exists but is not theirs tells them something about another
Organiser's work that they had no way to know.

A second submit answers `409` with a `reason` — `already-submitted`,
`not-owner` or `not-draft` — so the client can say which rule refused rather
than showing a generic failure.

Some schema shapes are worth knowing when reading this code:

- `events.proposed_date` is nullable so an Organiser may save a partial Draft.
  Submission still requires a date. Draft creation and saving require at least
  one letter or number across their fields, and preserve entered text exactly.
- `status_changes.old_status` is `NOT NULL`, so there is no row that can mean
  "created". The first entry in an event's history is derived from the event's
  own `created_at` and organiser instead — which is the honest model anyway:
  creating an event is not a change of status, it is the first one.
- `events.end_date` is the one column this project has added to the schema, in
  Event requests need an end time and there was nowhere to put one. It is
  nullable, because every draft and every row that predates it has no end time
  and inventing one would be worse than leaving it absent.

### Draft-to-submit flow

The active implementation uses the draft flow, not a separate request endpoint:

- `POST /events` creates a new event in `Draft` state.
- `PUT /events/{id}` edits the draft without changing its status.
- `POST /events/{id}/submit` moves it to `Submitted` once.

This matches the product flow in the current frontend: the organiser creates a
Draft first, then submits it when ready. The event still carries the same audit
trail, with the first status change recorded as `Draft -> Submitted`.

### Requesting clarification (US7.3)

A Coordinator asks the Organiser for information or a change, and the event moves
to Under Review.

```bash
curl -X POST http://localhost:8000/events/12/clarification \
  -H "Authorization: Bearer <coordinator token>" \
  -H 'Content-Type: application/json' \
  -d '{"message":"Please confirm the catering budget."}'
```

**There is no new table.** The message goes in `status_changes.notes`, a column
the schema has always had and nothing wrote until now, on the row that records
the clarification entry. If Lead assignment already moved the event to Under
Review, this entry keeps the same status and records the Coordinator's message.

That is also how "visible to the Organiser" is satisfied without any delivery
mechanism: the owning Organiser already reads the event's history, so the message
arrives there. `StatusChangeOut.notes` is empty on every automatic entry, which
is what lets a client tell a request apart from a plain status change.

Only the assigned Coordinator may ask. US8.1's shared event visibility check
applies before the clarification status rule.

Allowed from `Submitted` and from `Under Review`; a second question is still a
question, and refusing a follow-up would mean a Coordinator had one chance to
ask. A decided event answers `409` with `already-decided`. A `Draft` answers
`404` before the rule is reached, because a Coordinator cannot see one — the
`not-yet-submitted` refusal exists for completeness and is unreachable through
the route.

The Organiser's reply is a change request — see **US11.1** below.

### Approving and rejecting (US7.1/US4.3)

Only an assigned Coordinator can decide an event, and only while it is Under
Review. Approval moves it to Approved. Rejection moves it to Rejected and needs
a non-empty reason of at most 2,000 characters. The reason reuses
`status_changes.notes`, so it appears in the Organiser's existing audit trail.

The workflow allowlist lives in `app/event_status.py`, alongside US4.2's submit
rule: Draft -> Submitted, Submitted -> Under Review, and Under Review -> either
Approved or Rejected. Routes return `409` with `invalid-transition` for other
moves. Status validation remains in Python; there is no status SQL trigger and
US8.1's coordinator assignment is unchanged. Existing Supabase projects must run
[`SUPABASE_ATOMIC_EVENT_DECISIONS.sql`](SUPABASE_ATOMIC_EVENT_DECISIONS.sql)
before deploying this story. Its RPC only makes the conditional decision update
and audit insert atomic; it does not decide which transitions are valid.

While a change request is waiting (US11.1, below), approving or rejecting the
event answers `409` with `change-pending`: the Coordinator reviews the proposed
changes before deciding.

### Pending Safety Check (US4.4)

A ninth step sits between Planning and Confirmed. The allowlist in
`app/event_status.py` gains Planning → Pending Safety Check, Pending Safety
Check → Confirmed and Pending Safety Check → Planning; nothing else leads to
Confirmed.

- **Sending.** The assigned Coordinator sends the event once it is ready
  (`app/safety_check.py`): at least one Confirmed venue booking, no booking
  still Requested or Held, no Confirmed booking flagged “Conflict – review
  needed”, every equipment line Reserved, and no change request waiting.
  `GET /events/{id}/safety-check` says which of those is outstanding, so the
  page can explain rather than just disable the button. A refused send answers
  `409` with the same `reason`.
- **Deciding.** The Safety Officer can open an event only while it is Pending
  Safety Check. Approve moves it to Confirmed; sending it back moves it to
  Planning and needs a note (at most 2,000 characters), which lands in the
  audit trail and is sent to the assigned Coordinator (US10.2). US17.2 splits
  that into separate reject and request-changes outcomes.
- **Audit.** Every move is a `status_changes` row with who and when (US4.2).

Run [`SUPABASE_ADD_SAFETY_CHECK_STATUS.sql`](SUPABASE_ADD_SAFETY_CHECK_STATUS.sql)
first. Its two RPCs make each move and its audit row atomic, and the send RPC
re-checks readiness with the event locked. Its trigger is the backstop for any
other status write: an event becomes Confirmed only from Pending Safety Check,
and Pending Safety Check only from Planning.

Until US19.3 adds reserving equipment, an event with any equipment request
cannot be sent; remove the lines it does not need, or wait for US19.3.

### Cancelling an event (US4.6)

The owning Organiser, or the assigned Coordinator once the event is submitted,
cancels any event that is not Completed, Cancelled or Rejected, with a reason
(`app/event_cancellation.py`).

```bash
curl -X POST http://localhost:8000/events/12/cancel \
  -H "Authorization: Bearer <token>" \
  -H 'Content-Type: application/json' \
  -d '{"reason":"Funding was withdrawn."}'
```

- **One transaction.** The `cancel_event` RPC moves the event to Cancelled with a
  history entry (who, when, reason), cancels every booking that still holds its
  venue (Requested, Confirmed, a hold not yet expired) and removes every equipment
  line, so the slots and quantities are free. A cancelled Confirmed booking keeps
  the decision that confirmed it.
- **Afterwards, best effort.** Conflict flags at the freed venues are re-checked
  (US15.2), and the Organiser or Coordinator (whoever did not cancel), every Venue
  Staff user (if bookings were released) and every Tech Support user (if equipment
  was) get a Cancelled notice. Venue Staff now hold `notifications:read`.
- **Read-only.** Every route that changes the event, its bookings, holds or
  equipment refuses it; saving and cancelling a booking answer `409`
  `event-cancelled`.
- **Refusals.** `404` for an event that is not the caller's; `409`
  `already-cancelled`, `event-completed` or `event-rejected`; `400` for a missing
  reason or one over 2,000 characters.
- **Not built:** registrations marked Event Cancelled and notices to registered
  Attendees. Neither exists yet; see `tests/test_cases_us4_6.md` for what to add
  when the registration epic lands.

Run [`SUPABASE_US4_6_CANCEL_EVENT.sql`](SUPABASE_US4_6_CANCEL_EVENT.sql) first.

### Safety Officer review (US17.1)

`GET /events/{id}/safety-review` is everything the Safety Officer needs to
assess an event, so they do not have to chase anyone for it
(`app/safety_review.py`):

- the event's expected attendance and accessibility requirements (plus its
  preferred layout, venue requirements, and when it started waiting);
- each **booked** venue — bookings that hold their venue; Cancelled, Rejected
  and expired ones are history — with its capacity against the booking's
  headcount (`overCapacity`), the layout asked for against the ones it supports,
  its accessibility features against what the booking asked for, and its
  **known restrictions**: operating hours, setup and turnaround minutes (US9.4),
  and unavailability periods (US12.1) that have not ended yet;
- the **reserved** equipment lines (`Reserved`, set by US19.3; empty until then).

It is read-only (GET only; anything else answers `405`) and Safety Officer only
(`403` for every other role). As with the event itself, the Safety Officer can
reach it only while the event is Pending Safety Check; otherwise `404`. No
migration is needed.

### Requesting changes to a submitted event (US11.1)

Once an event is submitted, its Organiser no longer edits it directly — a
`PUT` on a non-Draft answers `409` with `change-request-required`. They fill in
the same edit form instead, and what they send becomes a proposal for the
assigned Coordinator to review. The event keeps its current details until the
Coordinator approves.

```bash
# Organiser: the edit form's values, plus an optional note (up to 2,000 characters)
curl -X POST http://localhost:8000/events/12/change-request \
  -H "Authorization: Bearer <organiser token>" \
  -H 'Content-Type: application/json' \
  -d '{"title":"Welcome Night","purpose":"Welcome the new intake.","description":"Talks.",
       "startsAt":"2027-11-02T19:00","endsAt":"2027-11-02T22:00","expectedAttendance":150,
       "note":"Moved to 19:00 as you asked."}'

# Coordinator: apply them, or keep the current details with a reason
curl -X POST http://localhost:8000/events/12/change-request/approve \
  -H "Authorization: Bearer <coordinator token>"
curl -X POST http://localhost:8000/events/12/change-request/reject \
  -H "Authorization: Bearer <coordinator token>" \
  -H 'Content-Type: application/json' \
  -d '{"reason":"The hall is booked at 19:00."}'
```

**What a request does.** The server compares the form's values with the
event's and records one row per field that differs. Text is compared exactly;
dates are compared as moments, so `18:00` and `18:00:00` are not a change. The
event moves to Under Review only if it is assigned and still Submitted. An
unassigned Submitted event stays in the Lead's queue; Under Review, Approved
and Planning keep their statuses and carry the pending flag.
The response carries:

- `changeRequested` — the "change requested" flag, true while a request waits;
- `pendingChanges` — each field's label, current and proposed value, and
  whether it is `important`;
- `changeRequestNote` — the Organiser's note while a request is pending;
- `lastChangeReview` — the Coordinator's answer to the most recent request:
  `approved` or `rejected`, when, the reason, and that request's Organiser note
  in `requestNote`.

**Important changes** follow US5.2's logging rule: date/time (`proposed_date`,
`end_date`), attendance, venue and equipment. Venue and equipment are in the
rule but are not columns on `events` yet, so no request can contain them until
the booking work adds them.

**Validation.** A request is checked as a submission, not as a draft, because a
submitted event has to stay complete: title, purpose, a date that is not in the
past, attendance of at least 1, and an end after the start. A request that
changes nothing answers `400`.

**Refusals** answer `409` with a `reason`:

| Reason | When |
| ------ | ---- |
| `not-submitted` | The event is still a Draft — edit it directly instead |
| `already-decided` | The event is Rejected, Confirmed, Completed or Cancelled |
| `already-pending` | A request is already waiting; one at a time |
| `nothing-pending` | Approve or reject was called with no request waiting |
| `invalid-transition` | Someone else acted on the event first; refresh and retry |

Another Organiser's event answers `404`, as everywhere else in this API.

**Storage.** Everything about a request lives in its own table,
`event_change_requests`: one row per proposed field, with `status`
(`pending` → `approved` or `rejected`), who asked and when, and who answered,
when and why. No other table's columns change:

- `events` gets approved values. A request on an assigned Submitted event moves
  it to Under Review; unassigned Submitted, Under Review, Approved and Planning
  retain their status.
- `status_changes` gets a row only when the status actually moves. The note is
  also stored on the request rows, so it remains visible for flag-only requests.
- `event_changes` stays a log of changes that were actually applied. An
  approved request writes its fields there when it is applied, with the same
  `important`/`routine` `change_type` as a US5.2 edit; the approving
  Coordinator is recorded as `changed_by_user_id`. A pending or rejected
  request never writes there.

"Change requested" is worked out rather than stored: an event has a request
waiting exactly when it has `pending` rows.

Existing Supabase projects must run
[`SUPABASE_ADD_CHANGE_REQUESTS.sql`](SUPABASE_ADD_CHANGE_REQUESTS.sql) before
deploying this story; every events route reads the new table. Its two RPCs make
each request and each answer atomic, and lock the event row so two requests or
two answers cannot slip past each other. Validation stays in Python, in
`app/change_requests.py` and `app/events.py`.

US4.5 additionally requires [`SUPABASE_US4_5_LIFECYCLE.sql`](SUPABASE_US4_5_LIFECYCLE.sql)
after the assignment, booking-needs and change-request scripts. Apply it before
deploying the US4.5 backend, because event reads select `request_note` and the
new writes use its atomic RPCs. The old round-robin backfill is retired; assign
unassigned events through the Lead's queue.
### Venue bookings (US14.1)

An assigned Coordinator requests one or more venues for an event, so a bigger
event can use a main hall and its breakout rooms at once (Week 7 change #3).

```bash
curl -X POST http://localhost:8000/events/12/bookings   -H "Authorization: Bearer <coordinator token>"   -H 'Content-Type: application/json'   -d '{"venueId":"1","startsAt":"2027-11-02T09:00","endsAt":"2027-11-02T17:00"}'
```

**Each booking is its own row** in `venue_bookings` (event, venue, start, end,
status), and each request creates exactly one. A main hall and two breakout rooms
are three calls, so a venue that is refused never takes another with it: the hall
is already stored before the breakout room is sent. US15.1 (availability) and
US18.1 (suitability) add their checks per booking, in `request_booking`. Existing
Supabase projects must run
[`SUPABASE_ADD_VENUE_BOOKINGS.sql`](SUPABASE_ADD_VENUE_BOOKINGS.sql) first. The
story asks for a single venue column on `events` to be migrated if one existed;
none ever did, so there was nothing to move.

- **Who.** Only the assigned Coordinator (US8.6). The `bookings:request`
  permission admits the role, and the event's readable check admits the
  assignment, answering `404` to a Coordinator the event is not assigned to — the
  same answer US8.1 gives for the event itself. The owning Organiser and the
  assigned Coordinator can both read the bookings.
- **Status.** Every new booking is `Requested` and waits for Venue Staff; the
  `booking_status` enum holds only that value until the Venue Booking Approval
  epic adds the rest.
- **Which events.** Approved and Planning only. The first successful request
  moves Approved to Planning with an audit entry; later requests leave Planning
  unchanged. Submitted and Under Review answer `not-approved`; Confirmed,
  Rejected, Cancelled and Completed answer `event-closed`.
- **Validation.** A venue that is in the catalogue, and a start and an end as
  `YYYY-MM-DDTHH:MM` (seconds optional), with the end after the start and the
  start not on a past date. Each refusal is a `400` with `invalid_booking` and a
  sentence naming one problem. The times need not match the event's own: a
  breakout room may be wanted for the afternoon only, or the hall the night
  before. Two bookings of the same venue are allowed; whether they clash is
  US15.1's to judge.

### Cancelling a booking (US14.2)

The assigned Coordinator cancels one booking, with a reason, without touching
anything else.

```bash
curl -X POST http://localhost:8000/events/12/bookings/31/cancel \
  -H "Authorization: Bearer <coordinator token>" \
  -H 'Content-Type: application/json' \
  -d '{"reason":"Numbers dropped, so the hall is too big."}'
```

- **What changes.** Only that booking's row: `Requested` → `Cancelled`, with
  `cancelled_at`, `cancelled_by_id` and `cancellation_reason` set on it, and
  `cancellation` (`at`, `byId`, `byName`, `reason`) in the response. The event's
  status, its history and its other bookings are not written. A cancelled booking
  stays on the event's list, so the Organiser can see what was dropped and why.
  Existing Supabase projects must run
  [`SUPABASE_CANCEL_VENUE_BOOKINGS.sql`](SUPABASE_CANCEL_VENUE_BOOKINGS.sql)
  after the US14.1 script.
- **The venue is freed.** `HOLDS_VENUE` in `app/booking_store.py` is the set of
  statuses that hold a venue for their slot, and `Cancelled` is not in it, so
  US15.1's conflict check will not count a cancelled booking. Requesting the same
  venue for the same slot again is a new booking.
- **Who and when.** The same rule as requesting (US8.6), under the same
  `bookings:request` permission. Allowed whatever the event's status: cancelling
  the hall for a Rejected event is how it is given back.
- **Refusals.** A booking that is missing, or on another event, answers `404`
  with `booking_not_found`. An already cancelled booking answers `409` with
  `already-cancelled`, including when two cancels race: the update only matches
  a booking that is still Requested. A blank reason, or one over 2,000
  characters, answers `400` with `invalid_booking`.

### Holds expire automatically (US14.4)

A Supabase **pg_cron** job runs `sweep_tentative_holds()` every 15 minutes. It
moves every hold past its expiry from Held to **Expired** and sends the event's
Coordinator a "Hold expired" notice, and it sends a "Hold expiring" notice once
when a hold has less than 24 hours left. The notices are worded exactly as
`notify_hold_expiring` and `notify_hold_expired` word them.

- **The slot is free at the deadline, not at the next sweep.** Every availability
  check still compares the expiry with the clock (US14.3); a Held hold past its
  expiry reads exactly like an Expired one (`Booking.hold_expired`).
- **Expired is history.** It stays on the event's bookings and the venue's holds
  list, never holds its venue, and requesting or cancelling it answers `409`
  `hold-expired`.
- **No backend scheduler.** The job lives in the database, so it runs whether or
  not anyone has the API up.

Rolling it out takes two scripts, at different times:

1. [`SUPABASE_US14_4_HOLD_EXPIRY.sql`](SUPABASE_US14_4_HOLD_EXPIRY.sql) — any time.
   Adds the status, the `expiry_warned_at` column and the function; changes
   nothing until something calls it.
2. [`SUPABASE_US14_4_SCHEDULE_HOLD_SWEEP.sql`](SUPABASE_US14_4_SCHEDULE_HOLD_SWEEP.sql)
   — **only after US14.4 is merged and everyone has pulled.** Older code cannot
   read the Expired status, so once the job writes it their booking pages answer
   500.

Run the sweep by hand with `SELECT public.sweep_tentative_holds();`. The SQL is
tested against the real database by `tests/test_hold_expiry_db.py`, which is
opt-in (`SPMG3T7_DB_TESTS=1`) and rolls everything back.

### Venue suitability (US18.1)

Before a venue is requested, the system says whether it suits the booking:
Suitable, or Not suitable with every reason. A venue that is not suitable cannot
be requested.

```bash
curl -X POST http://localhost:8000/events/12/bookings/suitability \
  -H "Authorization: Bearer <coordinator token>" \
  -H 'Content-Type: application/json' \
  -d '{"venueId":"3","startsAt":"2027-11-02T13:00","endsAt":"2027-11-02T15:00",
       "headcount":40,"layout":"Classroom","facilities":["projector"],
       "accessibilityNeeds":["step-free access"]}'
# {"venueId":"3","suitable":true,"reasons":[],"notes":[]}
```

- **What a booking needs** is on the booking, not the event: its own
  `headcount`, and an optional `layout`, `facilities` and `accessibilityNeeds`.
  The headcount defaults to the event's expected attendance when left out, so a
  breakout room in a multi-venue event (Week 7 change #3) is checked against the
  people in that room, not the whole event. All four are stored with the booking
  and returned on it. Existing Supabase projects must run
  [`SUPABASE_ADD_BOOKING_NEEDS.sql`](SUPABASE_ADD_BOOKING_NEEDS.sql), which also
  copies each existing booking's headcount from its event.
- **The rule** is [`app/suitability.py`](app/suitability.py), and it is pure: a
  venue and a booking's needs in, a verdict out. Not suitable if the headcount is
  more than the capacity (equal is suitable), the layout is not one the venue
  supports, a facility or accessibility need is not listed, or the booking runs
  outside the venue's operating hours on any day it touches.
- **Matching.** Layouts match whole, ignoring case and spacing. Facilities and
  accessibility needs match as a case-insensitive substring of a listed item, as
  US9.3's filter does, so "projector" is met by "twin projectors". Venue fields
  are read both as plain lists and as Postgres array literals (`{stage,"AV
  system"}`), which is how the seeded catalogue holds them.
- **Missing data.** A need is only met if the venue lists it, so a venue with no
  layouts recorded supports none. Operating hours are a limit rather than a
  feature, so hours that are not recorded, or that cannot be read, are not held
  against the venue: the verdict carries a `note` saying the time was not
  checked. Hours read as clauses like `08:00-22:00`, `Mon-Sat 08:00-22:00` or
  `Weekdays 09:00-17:00`, comma-separated; a closing time of `23:59` means
  midnight. Overnight hours (`22:00-02:00`) are not read.
- **Enforced, not just shown.** `POST /events/{id}/bookings` runs the same
  `assess` and answers `409` with `not-suitable` and the same `reasons` list
  when it fails. The check takes exactly the request's body and is refused the
  same ways (`404`, then `409`, then `400`), so the form and the rule agree.

### Registering for an event (US20.1)

The assigned Coordinator turns registration on for an event and sets its
capacity; Attendees see the Confirmed events taking registrations and register
for one ([`app/registrations.py`](app/registrations.py)).

```bash
# Coordinator: turn it on. Without "capacity", the expected attendance is used.
curl -X PUT http://localhost:8000/events/12/registration \
  -H "Authorization: Bearer <coordinator token>" \
  -H 'Content-Type: application/json' \
  -d '{"open":true,"capacity":50}'

# Attendee: what is open, then register.
curl http://localhost:8000/attendee/events -H "Authorization: Bearer <attendee token>"
curl -X POST http://localhost:8000/attendee/events/12/registrations \
  -H "Authorization: Bearer <attendee token>" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Casey Tan","email":"casey@example.com"}'
```

- **Settings.** `PUT /events/{id}/registration` takes `open` and an optional
  `capacity`, a whole number of at least 1. Left out, the stored capacity is
  kept, or the expected attendance used the first time. Allowed from Approved to
  Confirmed, so it can be opened before Attendees can see the event; `409`
  `not-approved` before that and `event-closed` (or US4.6's `event-cancelled`)
  after. A capacity below the places already taken is `409`
  `below-registered`. `GET` on the same path reads the settings and the places
  taken, for anyone who can open the event.
- **What Attendees see.** `GET /attendee/events` lists Confirmed events with
  registration on, soonest first: the name, when, the venues of its Confirmed
  bookings and the places left, and whether the caller is registered. Nothing
  else about the event is sent. An event not open is `404` `event_not_open`.
- **Registering.** A name and an email, both required (`400`
  `invalid_registration`, one problem at a time). One active registration per
  Attendee per event (`409` `already-registered`); none past the capacity
  (`409` `event-full`, "Event is full.").
- **Enforced in the database.** `register_for_event` locks the event row before
  it counts, so two Attendees after the last place queue on the lock and the
  second is told the event is full. A trigger re-checks any other write the same
  way, and a partial unique index holds one active registration per Attendee.
- **Full notice.** The registration that takes the last place tells the
  assigned Coordinator and the Organiser (kind `event-full`), best effort.
- **Attendee accounts.** `python seed_new_users.py --attendees-only` creates
  `attendee@spmg3t7.edu` and `attendee2@spmg3t7.edu`.

Run [`SUPABASE_US20_1_REGISTRATION.sql`](SUPABASE_US20_1_REGISTRATION.sql)
first. [`TEST_US20_1_REGISTRATION.sql`](TEST_US20_1_REGISTRATION.sql) checks it in
the SQL Editor and saves nothing, and `tests/test_registration_db.py` (opt-in,
`SPMG3T7_DB_TESTS=1`) also tries two registrations at the same moment.

### Seeing and withdrawing registrations (US20.2)

```bash
# The Attendee's registrations, one per event, with each event as it is now.
curl http://localhost:8000/attendee/registrations -H "Authorization: Bearer <attendee token>"

# Withdraw one, before the event starts.
curl -X POST http://localhost:8000/attendee/registrations/5/withdraw \
  -H "Authorization: Bearer <attendee token>"
```

- **The list** gives, per event, the newest registration: its status
  (Registered or Withdrawn), the name and email it was made with, when it was
  made or withdrawn, and the event's current title, date, time and venues. It
  also says whether the Attendee can withdraw (`canWithdraw`) or register again
  (`canRegisterAgain`), and the places left while the event takes registrations.
- **Withdrawing** is allowed while the event is Confirmed and before its start
  (Singapore time). `404` for a registration that is not the caller's; `409`
  `already-withdrawn`, `event-started` or `event-closed`. The database function
  `withdraw_registration` locks the event before the row, as registering does,
  and the row is kept as Withdrawn with `withdrawn_at`. The place counts as free
  at once.
- **Registering again** is US20.1's route: a withdrawn registration no longer
  counts, so a new one is taken while places are left.

Run [`SUPABASE_US20_2_WITHDRAW.sql`](SUPABASE_US20_2_WITHDRAW.sql) after the US20.1
script; [`TEST_US20_2_WITHDRAW.sql`](TEST_US20_2_WITHDRAW.sql) checks it in the SQL
Editor and saves nothing.

### Who registered (US20.3)

```bash
curl http://localhost:8000/events/12/registrations -H "Authorization: Bearer <token>"
# {"eventId":"12","open":true,"capacity":50,"registered":1,"placesLeft":49,
#  "registrations":[{"id":"5","name":"Casey Tan","email":"casey@example.com",
#                    "status":"Registered","registeredAt":"…","withdrawnAt":""}]}
```

- **Who.** The owning Organiser and the assigned Coordinator. The
  `registrations:read` permission admits those two roles; the event check admits
  only the Organiser's own events and the Coordinator's assigned ones, answering
  `404` otherwise. The Coordinator Lead, Venue Staff, the Safety Officer, Tech
  Support and Attendees get `403`: the list is personal data.
- **What.** One entry per person, their newest registration, in the order they
  registered: name, email, when, and Registered or Withdrawn (with when). The
  count is places taken against the capacity.
- **No database change**: it reads what US20.1 and US20.2 store.

## Venues

Four stories over one table, and they do not share a role. A Coordinator reads
the catalogue (US9.2) and narrows it (US9.3); Venue Staff create, update and
delete the records in it (US9.1a-c).

| Route                 | Who              | Purpose                                          |
| --------------------- | ---------------- | ------------------------------------------------ |
| `GET /venues`         | Coordinator, Venue Staff | The catalogue, by name; filtered (US9.2, US9.3) |
| `GET /venues/{id}`    | Coordinator, Venue Staff | One venue record                         |
| `POST /venues`        | Venue Staff only | Add a venue (US9.1a)                             |
| `PUT /venues/{id}`    | Venue Staff only | Update a venue (US9.1b)                          |
| `DELETE /venues/{id}` | Venue Staff only | Remove a venue — a hard delete (US9.1c)          |

Reading and writing are separate permissions held by different roles, so this is
not a hierarchy with Venue Staff at the top: they hold no event permission at
all, and a Coordinator's `POST /venues` is refused. Neither is a superset of the
other, which is why there are four venue permissions rather than one.

Unlike `events`, there is no per-record rule. Every venue is visible to every
Coordinator and writable by any Venue Staff member, so the role is the whole of
the guard and `require_permission` is the whole of the check. A venue that is not
in the catalogue answers `404` with `venue_not_found`.

### Filtering (US9.3)

Query parameters on the list route. No new table and no new endpoint — a bare
`GET /venues` is still the request US9.2 made.

| Parameter       | Matches                                                      |
| --------------- | ------------------------------------------------------------ |
| `minCapacity`   | `capacity >= value`. A whole number; `0` and up              |
| `location`      | Case-insensitive substring of `venues.location`              |
| `accessibility` | Case-insensitive substring of `venues.accessibility_features` |

```bash
# Venues holding at least 200 that are in the Library and have step-free access
curl 'http://localhost:8000/venues?minCapacity=200&location=Library&accessibility=step-free' \
  -H "Authorization: Bearer <token>"
```

Three things about how they behave:

- **They AND.** Every supplied criterion has to match. A Coordinator asking for
  200 seats *and* step-free access wants both, and returning the union would
  hand back exactly the rows they ruled out.
- **An empty parameter is not a filter.** `?location=` and `?location=%20` both
  return the whole catalogue, so a form that submits its untouched boxes does
  not accidentally narrow anything.
- **The text is literal.** `%` and `_` are escaped before the pattern reaches
  Postgres, so typing `100%` looks for a per-cent sign rather than matching
  everything.

Filtering happens in the database rather than in Python, for the reason
`list_events` gives: a catalogue narrowed before it leaves Postgres is one this
process cannot forget to narrow. A filter that cannot be read — `minCapacity=abc`,
a negative, a 300-character location — answers `400` with `invalid_filter` and a
sentence, rather than FastAPI's `422`, so a bad filter reads like every other
refusal this API sends.

### Writing a record (US9.1a-c)

`name`, `location` and a positive `capacity` are required. `facilities`,
`accessibilityFeatures`, `supportedLayouts` and `operatingHours` are optional and
may be left empty.

`id` and `created_at` are system-generated and are not in `VenueInput`, so there
is no field for them to arrive in and no path through the store that could move
them. That is US9.1b's rule kept by construction rather than by a check someone
has to remember; a request carrying an `id` changes nothing instead of being
refused. `updated_at` is the system's too, and the store stamps it.

`venues.name` is `UNIQUE`, so a clash answers `409` with `venue_name_taken` and
the name in the message — a rule, not a constraint violation leaking out. A venue
keeps its own name, so saving one unrenamed is not a clash.

The delete is a hard delete. A venue that any event has booked (US14.1) is in
use and answers `409` with `venue_in_use` instead: deleting it would either take
the event's booking with it or, since `venue_bookings.venue_id` has no cascade,
fail in the database. A cancelled booking (US14.2) still counts. It frees the
venue's slot, but it is still the event's record of what was asked for. Deleting a venue that is already gone answers `404` rather
than a quiet `204`: the caller is usually working from a stale list, and saying
so is more use than pretending it worked.

### Nullable columns

`venues.facilities`, `accessibility_features`, `operating_hours` and
`supported_layouts` are all nullable. An empty field is stored as `NULL` and read
back as `""`, and the page shows "Not recorded" — a venue nobody has filled in is
worth telling a Coordinator about, so the field is never silently dropped.
`venues.capacity` is `NOT NULL`.

### Schema and seed data

Two SQL scripts, both idempotent and both run once in the Supabase SQL Editor:

- [`SUPABASE_ADD_VENUE_LAYOUTS.sql`](SUPABASE_ADD_VENUE_LAYOUTS.sql) — **required
  before any venue route works, reads included.** US9.1a names supported layouts
  as a field and there was no column for it, so this adds
  `venues.supported_layouts`. Every venue route selects the column and both
  write routes send it, so a database without it answers `500` to all five —
  the backend log shows `PGRST204` naming the column. No restart is needed
  afterwards; PostgREST picks the column up on its own.
- [`SUPABASE_SEED_VENUES.sql`](SUPABASE_SEED_VENUES.sql) — six demonstration
  venues, for a catalogue that would otherwise render its empty state. Optional:
  Venue Staff can add records through the app instead. `venues.name` is `UNIQUE`
  and the insert is `ON CONFLICT DO NOTHING`, so it will not overwrite a row that
  is already there.

One seeded venue (Bertha Room) deliberately leaves all four nullable columns
unset, because a half-filled record is the case the catalogue has to render
without looking broken.

### Refusals

Every refusal carries a `code` as well as a message, so a client can tell them
apart rather than showing "login failed" for all four:

| Status | `code`                | Meaning                                        |
| ------ | --------------------- | ---------------------------------------------- |
| 401    | `invalid_credentials` | Wrong email or password                        |
| 401    | `not_authenticated`   | No token, or one that is not valid any more    |
| 401    | `session_expired`     | Signed in, then idle for too long              |
| 403    | `forbidden`           | Signed in, but this role may not do it (US1.3) |

```json
{
  "detail": {
    "code": "forbidden",
    "message": "The Event Organiser role cannot view the user directory. That is available to: Event Coordinator.",
    "required": "users:read",
    "role": "Event Organiser"
  }
}
```

### Development accounts

There is no way to create an account from the app yet, so development accounts
are made by hand in the Supabase dashboard. Each one needs two records, because
two systems own different halves of a person: an Auth account holding the
password (Authentication → Users → Add user, with **Auto Confirm User** on, or
it cannot sign in), and a `public.users` row holding the name and role. They are
joined on email, so both must use the same address. One account per role:

| Email                      | Role              |
| -------------------------- | ----------------- |
| `organiser@spmg3t7.edu`    | Event Organiser   |
| `coordinator@spmg3t7.edu`  | Event Coordinator |
| `venuestaff@spmg3t7.edu`   | Venue Staff       |

These are development credentials, not secrets, and they must not survive into a
deployed environment. Creating them by hand is deliberate: nothing in the app
writes an account, so none can appear in a deployed environment by accident.

The role names are the values of the `user_role` enum in the database, which is
why they read as `Event Organiser` rather than `Organiser`. Postgres rejects
anything else, so a typo in a role name fails at the write rather than silently
creating a user nobody has permissions for.

Try the whole thing from a terminal:

```bash
# Sign in
curl -X POST http://localhost:8000/auth/login   -H 'Content-Type: application/json'   -d '{"email":"organiser@spmg3t7.edu","password":"Sprint1!demo"}'

# Then, with the token it returned, ask for something an Organiser may not have
curl http://localhost:8000/auth/users -H "Authorization: Bearer <token>"
# 403, and the body says why
```

### Roles and permissions

Two roles, each holding a set of named permissions. The catalogue lives in
[`app/permissions.py`](app/permissions.py) and is the single place the rules are
written down — the client keeps no copy of it, it just reads the permissions the
server put on the session.

| Role              | May                                                   |
| ----------------- | ----------------------------------------------------- |
| Event Organiser   | create, read own, and submit events                   |
| Event Coordinator | read submitted events, review and edit them, read the user directory, read the venue catalogue, request and cancel venue bookings for their events, open registration for their events |
| Venue Staff       | read the venue catalogue, and add, update and delete the records in it |
| Attendee          | see the Confirmed events taking registrations, and register for them (US20.1) |

A role arrives with the epic that gives it something to do, never before: a
role that can sign in but can do nothing is a dead end for whoever holds it.
Adding one means a row in `ROLE_PERMISSIONS`, a landing route, and nothing
else — which is how Venue Staff arrived with US9.1a-c and Attendee with US20.1.
A `users` row holding a role this build does not model is skipped by the
directory and refused at sign-in rather than being forced into a role it does
not have.

Several of the permissions above have no route behind them yet. They are
declared now so the roles mean something consistent as each epic lands, and so a
new route only has to name the permission it needs:

```python
@router.get("/events")
def list_events(
    user: Annotated[User, Depends(require_permission(Permission.EVENTS_READ_SUBMITTED))]
):
    ...
```

## Run the checks

These are the same three steps CI runs, so a green run here means a green run there:

```bash
ruff check .            # lint
python -m compileall -q app   # build
pytest                  # tests
```

The current backend coverage exercises the draft and submit flow used by the app.

## Environment variables

Read from the process environment, with `.env` loaded first for local
development. `.env` never overrides a variable that is already set, so CI and a
deployed environment keep control of their own configuration.

| Variable                    | Default                 | Purpose                                                 |
| --------------------------- | ----------------------- | ------------------------------------------------------- |
| `SUPABASE_URL`              | *required*              | Supabase project URL                                    |
| `SUPABASE_ANON_KEY`         | *required*              | Anon key — subject to Row Level Security                |
| `SUPABASE_SERVICE_ROLE_KEY` | *required*              | Service role key — full admin, backend only             |
| `SUPABASE_DB_URL`           | unset                   | Postgres connection string; optional, unused by the API  |
| `CORS_ORIGINS`              | `http://localhost:5173` | Comma-separated list of origins allowed to call the API |
| `SESSION_IDLE_MINUTES`      | `30`                    | Inactivity after which a session expires (US1.1)        |

The three required values have no defaults on purpose. A plausible-looking
default would let the API start and then fail on the first query; a missing one
is named at the point it is read, pointing at `.env.example`.

`SESSION_IDLE_MINUTES` is sent to the client on the session, so the browser signs
out on the same schedule instead of waiting to be refused. A value that is not a
positive whole number falls back to the default rather than switching the timeout
off.

The default matches the Vite dev server, so the frontend works locally with no
configuration. Deployed environments should set `CORS_ORIGINS` to the real
frontend URL.

## Continuous integration

## US19 equipment setup

1. Apply `SUPABASE_ADD_NOTIFICATIONS.sql` if US10.1 has not already been applied.
2. Run the full contents of `SUPABASE_ADD_EQUIPMENT_REQUESTS.sql` in your
   Supabase SQL Editor. The SQL is rerunnable and preserves existing equipment
   rows. It also installs an atomic equipment-request audit trail. Alternatively,
   put a Session Pooler connection string in the gitignored `backend/.env` as
   `SUPABASE_DB_URL` and run `.venv/Scripts/python.exe apply_equipment_migration.py`.
   `SUPABASE_DB_URL` is only for this optional migration runner; the API uses
   `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY`.
3. Run `.venv/Scripts/python.exe seed_new_users.py --tech-only`. It creates
   Bryan's `technicalsupport@spmg3t7.edu` Auth login and `Technical Support`
   profile. New Auth accounts use `PASSWORD`, which defaults to `Sprint1!demo`
   and can be overridden with `SEED_PASSWORD`. Existing passwords are not reset.
4. Start the API, then run `.venv/Scripts/python.exe seed_equipment.py`. It
   signs in through `/auth/login`, creates ten sample items through `/equipment`,
   and replaces their old generic demo descriptions on reruns. Other edits are
   preserved. Set `SEED_API_URL` if the API is not on
   `http://localhost:8000`.

Equipment requests do not reserve stock or change event status. US19.3 owns
availability checks and reservation. The migration prevents an event from
leaving Planning while any equipment line remains Requested.
The event's Organiser and assigned Coordinator see creation, edits, and
removals in the existing right-hand status history, in time order from Draft,
with actor, time, and changed values.

## Continuous integration

The `backend` job in [`../.github/workflows/ci.yml`](../.github/workflows/ci.yml)
runs on every push to `main` and on every pull request. It installs dependencies,
lints, byte-compiles the sources, and runs the test suite. A failing step fails
the build and blocks the PR.

It runs alongside the `frontend` job on every change, not only on changes under
`backend/` — the two halves call each other, so a green backend against a broken
client is not a useful signal.

## Project structure

```
app/
  main.py           FastAPI application and routes
  config.py         environment-driven settings
  auth.py           /auth routes, and the dependencies that guard a route
  permissions.py    roles, permissions, and which role holds what
  users.py          the user directory, backed by the Supabase users table
  sessions.py       session store with a sliding inactivity window
  security.py       session-token generation
  supabase_client.py  the admin, anonymous and per-user Supabase clients
  events.py         /events routes — US4.1, US4.2, and US14.1's /events/{id}/bookings
  event_store.py    event data access, over the events and status_changes tables
  booking_store.py  venue booking data access, over the venue_bookings table
  suitability.py    whether a venue suits one booking — US18.1, no I/O
  event_status.py   the status label set, the submit rule and the US7.3 review rule
  venues.py         /venues routes — US9.1a-c, US9.2 and US9.3
  venue_store.py    venue data access, over the venues table
tests/
  conftest.py                 shared client and sign-in fixtures
  test_health.py
  test_config.py
  test_security.py            hashing and tokens
  test_sessions.py            expiry and revocation, on a clock the test controls
  test_supabase_config.py     which key each client carries
  test_users.py               the user directory over the Supabase table
  test_auth_login.py          US1.1
  test_auth_logout.py         US1.2
  test_access_enforcement.py  US1.3
  test_events.py              US4.1 and US4.2
  test_event_clarification.py US7.3, and the rule on its own
  test_venues.py              US9.1a-c, US9.2 and US9.3, through the routes
  test_venue_store.py         the Supabase venue queries, against a fake client
  test_venue_bookings.py      US14.1, through the routes
  test_venue_booking_cancellation.py  US14.2, through the routes
  test_venue_suitability.py   US18.1, through the routes
  test_suitability.py         the US18.1 rule on its own
  test_booking_store.py       the Supabase booking queries, against a fake client
```

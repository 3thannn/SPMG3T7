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

`SUPABASE_DB_URL` is optional and unused by the API, which goes through
PostgREST. It is there for reading the schema directly — inspecting Row Level
Security policies, say. If you do set it, use the **Session pooler** string
rather than the direct connection, which is IPv6-only and fails on most home
networks.

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
| `PUT /events/{id}`           | the owning Organiser          | Save edits; the status does not move       |
| `POST /events/{id}/submit`   | the owning Organiser          | Draft → Submitted, once (US4.2)            |
| `POST /events/{id}/clarification` | assigned Coordinator     | Ask for info or changes; → Under Review (US7.3) |
| `POST /events/{id}/approve`  | assigned Coordinator        | Under Review → Approved (US7.1)       |
| `POST /events/{id}/reject`   | assigned Coordinator        | Under Review → Rejected with a reason (US7.1) |
| `GET /events/{id}/bookings`  | owning Organiser, assigned Coordinator | The event's venue bookings, soonest first (US14.1) |
| `POST /events/{id}/bookings` | assigned Coordinator        | Request one venue; it starts Requested (US14.1) |
| `POST /events/{id}/bookings/{bookingId}/cancel` | assigned Coordinator | Cancel one booking with a reason (US14.2) |

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
the move to Under Review. The request and the status change it caused are one
event in the event's history, and storing them apart would let them disagree
about when it happened or who asked.

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

The Organiser's reply is **US11.1** and is deliberately not modelled here.

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
- **Which events.** Submitted, Under Review, Approved, Planning and Confirmed. A
  Rejected, Cancelled or Completed event answers `409` with `event-closed`. A
  booking is only a request until Venue Staff approve it, so asking while the
  event is still under review costs nothing.
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
| Event Coordinator | read submitted events, review and edit them, read the user directory, read the venue catalogue, request and cancel venue bookings for their events |
| Venue Staff       | read the venue catalogue, and add, update and delete the records in it |

Technical Support and Attendee are part of the wider plan and are deliberately
not modelled yet: a role that can sign in but can do nothing is a dead end for
whoever holds it. They come back with the epics that give them something to do,
and adding one means a row in `ROLE_PERMISSIONS`, a landing route, and nothing
else — which is exactly how Venue Staff arrived with US9.1a-c. The database already declares all five in `user_role`;
a row holding one of the other three is skipped by the directory and refused at
sign-in rather than being forced into a role it does not have.

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
  test_booking_store.py       the Supabase booking queries, against a fake client
```

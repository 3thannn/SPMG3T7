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

Then seed the development accounts:

```bash
python -m app.seed
```

There are no migrations to run. This project uses the schema exactly as it is —
`users`, `events`, `status_changes`, `venues`, `equipment` — and adds no columns
of its own. If a schema change ever becomes necessary, that is a conversation
with whoever owns the schema, not something the backend does on startup.

For a new project, run [`SUPABASE_SETUP.sql`](SUPABASE_SETUP.sql) once. For the
already-created project, run [`SUPABASE_HARDENING.sql`](SUPABASE_HARDENING.sql)
once in the Supabase SQL Editor. It adds the missing audit foreign-key index,
locks the timestamp trigger's search path, and makes the server-only Data API
access model explicit; it does not alter existing rows or table shapes.

Seeding is a command you run deliberately, not something that happens on
startup, so nobody creates development credentials in a deployed environment by
accident. It is idempotent: running it again after changing `SEED_PASSWORD`
resets the password rather than duplicating the accounts.

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
| `GET /events`                | Organiser (own), Coordinator (all) | The events list (US4.1)               |
| `GET /events/{id}`           | as above                      | One event, with its audit trail            |
| `POST /events`               | Organiser                     | Create — always lands in Draft (US4.2)     |
| `PUT /events/{id}`           | the owning Organiser          | Save edits; the status does not move       |
| `POST /events/{id}/submit`   | the owning Organiser          | Draft → Submitted, once (US4.2)            |

An event that belongs to another Organiser answers `404`, not `403`. Telling
someone an event exists but is not theirs tells them something about another
Organiser's work that they had no way to know.

A second submit answers `409` with a `reason` — `already-submitted`,
`not-owner` or `not-draft` — so the client can say which rule refused rather
than showing a generic failure.

The schema is used exactly as it stands, and two of its shapes are worth
knowing when reading this code:

- `events.proposed_date` is `NOT NULL`, so an event with no date is not
  something the database can hold. The create and save routes require one, and
  the form asks for it up front rather than accepting a draft it cannot store.
- `status_changes.old_status` is `NOT NULL`, so there is no row that can mean
  "created". The first entry in an event's history is derived from the event's
  own `created_at` and organiser instead — which is the honest model anyway:
  creating an event is not a change of status, it is the first one.

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

There is no way to create an account yet, so `python -m app.seed` writes one
account per role — an Auth account holding the password, and a `users` row
holding the name and role — both sharing the password `Sprint1!demo`:

| Email                     | Role              |
| ------------------------- | ----------------- |
| `organiser@spmg3t7.edu`   | Event Organiser   |
| `coordinator@spmg3t7.edu` | Event Coordinator |

These are development credentials, not secrets, and they must not survive into a
deployed environment. Set `SEED_PASSWORD` to change the shared password; drop
the seeding entirely once accounts can be created.

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
| Event Coordinator | read all events, review them, read the user directory |

Venue Staff, Technical Support and Attendee are part of the wider plan and are
deliberately not modelled yet: a role that can sign in but can do nothing is a
dead end for whoever holds it. They come back with the epics that give them
something to do, and adding one means a row in `ROLE_PERMISSIONS`, a landing
route, and nothing else. The database already declares all five in `user_role`;
a row holding one of the other three is skipped by the directory and refused at
sign-in rather than being forced into a role it does not have.

Several of the permissions above have no route behind them yet. They are
declared now so the roles mean something consistent as each epic lands, and so a
new route only has to name the permission it needs:

```python
@router.get("/events")
def list_events(user: Annotated[User, Depends(require_permission(Permission.EVENTS_READ_ALL))]):
    ...
```

## Run the checks

These are the same three steps CI runs, so a green run here means a green run there:

```bash
ruff check .            # lint
python -m compileall -q app   # build
pytest                  # tests
```

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
| `SEED_PASSWORD`             | `Sprint1!demo`          | Shared password for the seeded development accounts     |

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
  events.py         /events routes — US4.1 and US4.2
  event_store.py    event data access, over the events and status_changes tables
  event_status.py   the status label set and the submit rule
  seed.py           writes the development accounts (python -m app.seed)
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
```

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

| Route              | Who                | Purpose                                          |
| ------------------ | ------------------ | ------------------------------------------------ |
| `POST /auth/login` | anyone             | Exchange credentials for a session (US1.1)       |
| `POST /auth/logout`| anyone             | End the session immediately (US1.2)              |
| `GET /auth/me`     | any signed-in user | Who this token belongs to; used to restore a session |
| `GET /auth/users`  | Coordinator only   | The user directory — the first route behind the permission layer (US1.3) |

A session slides: every authenticated request extends it, so it survives normal
use and lapses only after `SESSION_IDLE_MINUTES` without one. Sessions are held
in memory, so restarting the API signs everyone out — the same gap as the rest
of the project's storage, and it closes with the database story.

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
    "message": "The Organiser role cannot view the user directory. That is available to: Coordinator.",
    "required": "users:read",
    "role": "Organiser"
  }
}
```

### Development accounts

There is no way to create an account yet, so one account per role is seeded at
startup, both sharing the password `Sprint1!demo`:

| Email                     | Role        |
| ------------------------- | ----------- |
| `organiser@spmg3t7.edu`   | Organiser   |
| `coordinator@spmg3t7.edu` | Coordinator |

These are development credentials, not secrets, and they must not survive into a
deployed environment. Set `SEED_PASSWORD` to change the shared password; drop
the seeding entirely once accounts can be created.

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

| Role        | May                                                   |
| ----------- | ----------------------------------------------------- |
| Organiser   | create, read own, and submit events                   |
| Coordinator | read all events, review them, read the user directory |

Venue Staff, Technical Support and Attendee are part of the wider plan and are
deliberately not modelled yet: a role that can sign in but can do nothing is a
dead end for whoever holds it. They come back with the epics that give them
something to do, and adding one means a row in `ROLE_PERMISSIONS`, a landing
route, and nothing else.

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

| Variable                | Default                 | Purpose                                                 |
| ----------------------- | ----------------------- | ------------------------------------------------------- |
| `CORS_ORIGINS`          | `http://localhost:5173` | Comma-separated list of origins allowed to call the API |
| `SESSION_IDLE_MINUTES`  | `30`                    | Inactivity after which a session expires (US1.1)        |
| `SEED_PASSWORD`         | `Sprint1!demo`          | Shared password for the seeded development accounts     |

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
  users.py          the user directory (seeded, in memory)
  sessions.py       session store with a sliding inactivity window
  security.py       password hashing and token generation
tests/
  conftest.py               shared client and sign-in fixtures
  test_health.py
  test_config.py
  test_security.py          hashing and tokens
  test_sessions.py          expiry and revocation, on a clock the test controls
  test_auth_login.py        US1.1
  test_auth_logout.py       US1.2
  test_access_enforcement.py  US1.3
```

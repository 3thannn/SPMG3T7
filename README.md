# SPMG3T7

Monorepo holding both halves of the SPMG3T7 project:

| Directory                | What it is                                    | Stack                          |
| ------------------------ | --------------------------------------------- | ------------------------------ |
| [`backend/`](backend/)   | REST API — authentication, roles, health check | Python 3.12, FastAPI, uvicorn  |
| [`frontend/`](frontend/) | Web client — sign-in, events, backend status   | Node 22, React 19, Vite, TypeScript |

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

Frontend:

```bash
cd frontend
npm install
```

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

Sign in with one of the seeded development accounts, both with the password
`Sprint1!demo`:

| Email                     | Role        | Can do                                |
| ------------------------- | ----------- | ------------------------------------- |
| `organiser@spmg3t7.edu`   | Organiser   | create, edit and submit their events  |
| `coordinator@spmg3t7.edu` | Coordinator | see every event, review them          |

These are development credentials, not secrets, and they must not survive into a
deployed environment. Signing in needs the API running — there is no way past
the form without it.

## Run the checks

These are exactly what CI runs, so green here means green there.

```bash
cd backend  && ruff check . && python -m compileall -q app && pytest
cd frontend && npm run lint && npm run build && npm test
```

## How the two halves connect

The frontend reads `VITE_API_BASE_URL` (default `http://localhost:8000`) to find
the API; the backend reads `CORS_ORIGINS` (default `http://localhost:5173`) to
decide who may call it. The defaults line up, so local development needs no
configuration. Change one and you must change the other.

| Variable               | Side     | Default                 | Purpose                                    |
| ---------------------- | -------- | ----------------------- | ------------------------------------------ |
| `VITE_API_BASE_URL`    | frontend | `http://localhost:8000` | Base URL of the backend API                |
| `CORS_ORIGINS`         | backend  | `http://localhost:5173` | Comma-separated origins allowed to call it |
| `SESSION_IDLE_MINUTES` | backend  | `30`                    | Inactivity after which a session expires   |
| `SEED_PASSWORD`        | backend  | `Sprint1!demo`          | Password for the seeded development accounts |

Copy [`frontend/.env.example`](frontend/.env.example) to `frontend/.env.local` to
override the frontend value. Only `VITE_`-prefixed variables reach the browser —
never put secrets in them.

## Continuous integration

Two workflows, one per half, each filtered by path so a change to one side does
not spend a runner on the other:

- [`.github/workflows/backend-ci.yml`](.github/workflows/backend-ci.yml) — runs on changes under `backend/`
- [`.github/workflows/frontend-ci.yml`](.github/workflows/frontend-ci.yml) — runs on changes under `frontend/`

Both run on every push to `main` and on every pull request that touches their
paths, and both lint, build and test. A failing step fails the build and blocks
the PR.

Note on branch protection: because of the path filters, a frontend-only PR never
starts Backend CI. If you mark these as *required* status checks, such a PR will
wait forever for a check that will not run. Either leave them unrequired, or drop
the `paths:` filters so both always run.

## Repository layout

```
backend/
  app/
    main.py            FastAPI application and routes
    config.py          environment-driven settings
    auth.py            /auth routes and the dependencies that guard a route
    permissions.py     roles, permissions, and which role holds what
    users.py           the user directory (seeded, in memory)
    sessions.py        session store with a sliding inactivity window
    security.py        password hashing and token generation
  tests/               one file per story, plus unit tests for each module
  pyproject.toml       ruff and pytest configuration
  requirements.txt     runtime dependencies
  requirements-dev.txt runtime + test/lint tooling (what CI installs)
frontend/
  src/
    main.tsx           React entry point
    App.tsx            root component: session, route guards, health status
    api.ts             backend client and its error types
    session.ts         the stored session, revived on load
    permissions.ts     which route needs which permission
    useIdleSignOut.ts  signs out after the server's idle window
    status.ts          event status model and roles
    pages/             sign-in, landing, events, event detail, access denied
    components/        top nav, status badge, status timeline
  index.html
  package.json
  vite.config.ts
.github/workflows/     one CI workflow per half
```

## History

This repo was formed by combining two previously separate repositories,
`SPMG3T7BackEnd` and `SPMG3T7FrontEnd`. Both histories are preserved — commits
made before the merge appear under their original messages and authors, with
their paths rewritten under `backend/` and `frontend/`. `git log --follow` on any
file works back through the merge.

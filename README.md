# SPMG3T7

Monorepo holding both halves of the SPMG3T7 project:

| Directory                | What it is                                    | Stack                          |
| ------------------------ | --------------------------------------------- | ------------------------------ |
| [`backend/`](backend/)   | REST API — health check, CORS, config          | Python 3.12, FastAPI, uvicorn  |
| [`frontend/`](frontend/) | Web client — login UI, backend status          | Node 22, React 19, Vite, TypeScript |

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

| Variable            | Side     | Default                 | Purpose                                     |
| ------------------- | -------- | ----------------------- | ------------------------------------------- |
| `VITE_API_BASE_URL` | frontend | `http://localhost:8000` | Base URL of the backend API                 |
| `CORS_ORIGINS`      | backend  | `http://localhost:5173` | Comma-separated origins allowed to call it  |

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
  tests/
    test_health.py
    test_config.py
  pyproject.toml       ruff and pytest configuration
  requirements.txt     runtime dependencies
  requirements-dev.txt runtime + test/lint tooling (what CI installs)
frontend/
  src/
    main.tsx           React entry point
    App.tsx            root component, shows backend connection status
    LoginForm.tsx      login UI
    api.ts             backend client
    test/setup.ts      Vitest setup (jest-dom matchers, cleanup)
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

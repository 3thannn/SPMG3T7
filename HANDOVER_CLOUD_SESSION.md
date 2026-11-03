# Handover to Cloud Session - SPMG3T7

**Date:** 2026-11-03
**Branch:** `chore/playwright-test-reduction-handover`
**Base:** `main`
**Repository:** https://github.com/sjzdylan/SPMG3T7

## Read this first: state of the branch

Verified by running the suites on this branch. See `TEST_AUDIT.md` for the method.

| Check | `main` (`a6c8213`) | This branch |
| --- | --- | --- |
| `pytest --cov` | 2,513 passed, 10 skipped, 100% | **1,557 passed, 10 skipped, 100.00%** |
| `ruff check .` and `compileall` | clean | clean |
| Frontend `npm test -- --coverage` | 1,406 passed, 100% lines | unchanged |
| Real-database tests (`integration/`, `*_db.py`) | untouched | untouched, identical to `main` |

The backend was cut from `main`'s full suite, keeping every test the test-case
documents cite, the tests for the customer's Week 7 and clarified rules, the
fewest others needed to hold 100% coverage, and one test per class or file.
The frontend was not reduced: the eight coverage-scaffold files were each tried
and each was needed to keep the 100% line threshold.

**Still open:**
1. A named team member must review that the kept tests assert the right things.
   The CSVs have blank `Reviewed By` and `Review Result` columns for that.
2. 11 frontend test titles cited in the docs are worded differently from the
   tests themselves.
3. The Postgres migration tests in `integration/` were not run here.

## What the branch changed

1. **Test inventory:** `test_inventory.csv` (one row per automated test, all layers) and `test_case_register.csv` (one row per documented test case), both made by `backend/generate_test_inventory.py`. Regenerate them with the script before quoting numbers. `TEST_INVENTORY_SUMMARY.md` is from the older version and is out of date.
2. **Test reduction:** commits `bdac5d0`, `37076ef`, `77bdbff`, `c2edddc` (plus later doc commits). These removed coverage-scaffolding tests, infrastructure test classes, and some parameterized cases. The intent was to cut the suite from about 2,504 tests, but the result is now below the 100% coverage gate and has one broken import.
3. **Docs:** `HANDOVER_CLOUD_SESSION.md` (this file) and `handover.md`.

## Setup

### Backend (Python 3.12 in CI; 3.13 also works locally)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env             # then fill in the values
```

Use `requirements-dev.txt`, not `requirements.txt`. It includes the test, coverage, and lint tools that CI uses.

Required `backend/.env` values (from `backend/.env.example`):

```env
SUPABASE_URL=https://YOUR-PROJECT-REF.supabase.co
SUPABASE_ANON_KEY=...            # used for sign-in, subject to RLS
SUPABASE_SERVICE_ROLE_KEY=...    # FULL ADMIN, backend only, never prefix with VITE_
```

Optional:

```env
# SUPABASE_DB_URL=postgresql://...   # only for apply_equipment_migration.py
# CORS_ORIGINS=http://localhost:5173
# SESSION_IDLE_MINUTES=30
```

`backend/.env` is gitignored. Never commit it.

### Database migrations

`backend/SUPABASE_SETUP.sql` creates the base schema. Apply the other `SUPABASE_*.sql` scripts in dependency order using the Supabase SQL Editor. The table in the root `README.md` lists each script, what it enables, and what breaks if it is skipped. Every script is idempotent. Note the order-sensitive chains, such as `SUPABASE_ADD_VENUE_BOOKINGS.sql` → `SUPABASE_CANCEL_VENUE_BOOKINGS.sql` → `SUPABASE_ADD_BOOKING_NEEDS.sql` → `SUPABASE_ADD_VENUE_HOLDS.sql` → `SUPABASE_ADD_BOOKING_DECISIONS.sql` → `SUPABASE_ADD_BOOKING_CONFLICTS.sql`.

### Frontend (Node 22+, npm 10+)

```bash
cd frontend
npm install
cp .env.example .env.local       # set VITE_API_BASE_URL (default http://localhost:8000)
npx playwright install           # only if running E2E
```

The frontend talks only to the API. It never talks to Supabase directly, so it needs only `VITE_API_BASE_URL`.

## Commands

### Backend

```bash
cd backend && source .venv/bin/activate
ruff check .                     # lint (CI step)
python -m compileall -q app      # build check (CI step)
pytest                           # all tests
pytest --cov                     # CI gate: must reach 100% line and branch coverage
pytest -k us20_1                 # one user story
pytest tests/test_venue_store.py # one file
```

The database tests in `backend/integration/` read `TEST_POSTGRES_DSN`, which must point to a disposable Postgres database. CI runs them against a Postgres 16 service. Without the variable they skip.

### Frontend

```bash
cd frontend
npm run lint                     # oxlint
npm test                         # vitest unit tests
npm run build                    # tsc -b && vite build
npm run test:e2e                 # Playwright (starts `npm run dev` on :5173)
npm run test:e2e:isolated        # isolated Playwright config
```

The E2E suite was not run during this handover. Run it before relying on it.

## Repository layout

- `backend/app/`: FastAPI modules, one per feature (`events.py`, `venues.py`, `holds.py`, `safety_decisions.py`, `registrations.py`, and so on), with `*_store.py` modules for data access.
- `backend/tests/`: `test_*.py` files, plus `test_cases_us*.md` specifications. Naming follows `test_<feature>_us<X>_<Y>.py`. Shared fixtures are in `conftest.py`, and fakes are in `fakes.py`.
- `backend/integration/`: database-backed tests.
- `frontend/src/`: React pages, components, and stores (`*Store.ts`).
- `frontend/e2e/` and `frontend/e2e-isolated/`: Playwright specs.
- `.github/workflows/ci.yml`: the CI pipeline (backend and frontend jobs run on every push and PR).

## Test classification (for the inventory)

- **Unit:** files with `_store.py` or `_repository.py` in their name, or tests of business logic in isolation.
- **Integration:** tests of API routes through FastAPI's `TestClient`.
- **E2E:** Playwright specs in `frontend/e2e/`.

## Next steps, in priority order

1. Fix the broken import and restore coverage to 100% (see "Read this first").
2. Get `ruff check .`, `compileall`, and `pytest --cov` green locally, then on the PR.
3. Regenerate `test_inventory.csv` and `TEST_INVENTORY_SUMMARY.md` from the fixed suite.
4. Run the frontend `npm test` and `npm run test:e2e`, and record the results.
5. Only then decide whether the pyramid needs more unit tests (currently about 37% unit, 61% integration, 2% E2E).

## Background services

If you started servers locally, stop them before switching branches:

```bash
lsof -ti:8000 | xargs kill 2>/dev/null   # backend
lsof -ti:5173 | xargs kill 2>/dev/null   # frontend dev server
```

## Context for the new session

Paste this into the new session:

```
I'm continuing work on SPMG3T7 (FastAPI + Supabase backend, React + Vite frontend).
Branch: chore/playwright-test-reduction-handover.
Read HANDOVER_CLOUD_SESSION.md first. The backend currently has one failing test
(missing FakeAdmin import in test_change_requests.py) and coverage is ~90%, below
the 100% CI gate. Please help me fix that first. My next task: [YOUR TASK].
```

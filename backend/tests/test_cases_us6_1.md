# Test Cases for US6.1: Project Setup, CI Pipeline and Developer Docs

> As a developer on the team, I want the backend and frontend set up with a CI
> pipeline and setup instructions, so that everyone can run the project and every
> change is checked the same way.

## Acceptance Criteria

| # | Criterion | Status |
| --- | --- | --- |
| AC1 | A FastAPI backend and a React + TypeScript frontend run locally | Done |
| AC2 | The frontend shows whether it can reach the backend (`GET /health`) | Done — "Backend connected" / "Backend unreachable" |
| AC3 | CI lints, builds and tests both halves on every push to `main` and every pull request | Done — one workflow, jobs `CI / backend` and `CI / frontend` |
| AC4 | The README covers prerequisites, setup, running both halves and the local equivalent of every CI step | Done |
| AC5 | Configuration comes from environment variables with defaults that work locally | Done — `VITE_API_BASE_URL`, `CORS_ORIGINS` |

## Test Case Design Approach
Following the 5-step test case design methodology:
1. Visualize Workflow
2. Happy Path (Positive Testing)
3. Cross-cutting Quality Expectations
4. Negative Testing
5. Boundary Testing

### Team assumptions (not customer-confirmed)
- **One CI workflow with a job per half and no `paths:` filters.** A check that only
  sometimes runs cannot be made a required check, because a pull request that skips
  it would wait for it forever. The halves also depend on each other: the client
  calls the API. The two jobs run in parallel.
- **The local commands are exactly what CI runs**, so green locally means green in CI.
- **The defaults line up**: the frontend calls `http://localhost:8000` and the
  backend allows `http://localhost:5173`, so local development needs no
  configuration. Change one and you must change the other.
- **Supabase keys are backend-only** and have no `VITE_` version, because only
  `VITE_` variables reach the browser.

## Workflow Visualization

```
push to main / open or update a PR
              │
              ▼
        GitHub Actions: CI
     ┌────────┴─────────┐   (in parallel)
  CI / backend        CI / frontend
  pip install         npm ci
  ruff check .        npm run lint   (oxlint)
  compileall app      npm run build  (tsc -b && vite build)
  pytest              npm test       (vitest)
     └────────┬─────────┘
   any step fails → the check fails and blocks the PR

Locally:  frontend (5173) ── GET /health ──► backend (8000) → {"status": "ok"}
          page shows "Backend connected", or "Backend unreachable" if it fails
```

## Test Files

| Layer | File |
| --- | --- |
| Backend | `test_health.py`, `test_config.py` (`CORS_ORIGINS`) |
| Frontend | `api.test.ts` (`apiBaseUrl`, `fetchHealth`), `App.test.tsx` (landing and health) |
| CI | `.github/workflows/ci.yml` |
| Docs | `README.md`, `backend/README.md`, `frontend/README.md` |

---

## 1. HAPPY PATH TEST CASES

### TC-P01: The backend answers its health check (AC1, AC2)
- **Test Steps**: `GET /health`
- **Expected Result**: 200, `{"status": "ok"}`
- **Automated**: `test_health_returns_ok`

### TC-P02: The frontend shows the backend is connected (AC2)
- **Pre-conditions**: the health check succeeds
- **Expected Result**: the landing page renders, with "Backend connected"
- **Automated**: frontend "renders the landing hero", "reports the backend as connected when the health check succeeds", "returns the parsed payload when the API responds"

### TC-P03: CI runs every check on a pull request (AC3)
- **Test Steps**: open or update a pull request
- **Expected Result**: `CI / backend` (ruff, compileall, pytest) and `CI / frontend` (oxlint, build, vitest) both run, whatever files changed
- **Manual**: check the PR's Checks tab

### TC-P04: The local checks match CI (AC3, AC4)
- **Test Steps**: from the README, `cd backend && ruff check . && python -m compileall -q app && pytest`, then `cd frontend && npm run lint && npm run build && npm test`
- **Expected Result**: the same steps CI runs, with the same result
- **Manual**: see §5

### TC-P05: A new developer can follow the README (AC4)
- **Test Steps**: on a fresh clone, follow "Prerequisites", "First-time setup" and "Run both halves"
- **Expected Result**: the API on port 8000, the app on port 5173, and the app shows "Backend connected"
- **Manual**

### TC-P06: Defaults work with no configuration (AC5)
- **Expected Result**: the frontend calls `http://localhost:8000`; the backend allows `http://localhost:5173`
- **Automated**: `test_defaults_to_local_frontend`; frontend "falls back to the local backend"

---

## 2. CROSS-CUTTING QUALITY EXPECTATIONS

### TC-P10: A failing step blocks the pull request
- **Expected Result**: a lint error, a type error or a failing test fails that job, and the PR shows a failed check
- **Manual**: seen on several PRs (e.g. PR #35 needed lint and test fixes before it went green)

### TC-P11: Configured CORS origins are read exactly
- **Test Steps**: `CORS_ORIGINS="https://a.example.com, https://b.example.com "`
- **Expected Result**: two origins, trimmed
- **Automated**: `test_splits_and_trims_configured_origins`

---

## 3. NEGATIVE TEST CASES

| ID | Scenario | Expected | Automated |
| --- | --- | --- | --- |
| TC-P20 | Backend not running, or the health check returns an error | "Backend unreachable" | frontend "reports the backend as unreachable when the health check fails", "throws when the API returns an error status" |
| TC-P21 | Unknown route | 404 | `test_unknown_route_returns_404` |
| TC-P22 | A Supabase credential missing from `backend/.env` | The error names the missing variable and where to put it | `test_a_missing_credential_names_itself_and_says_where_to_put_it` (US6.3) |

## 4. BOUNDARY TEST CASES

| ID | Boundary | Expected | Automated |
| --- | --- | --- | --- |
| TC-P30 | `CORS_ORIGINS` unset | Only `http://localhost:5173` | `test_defaults_to_local_frontend` |
| TC-P31 | `VITE_API_BASE_URL` unset | `http://localhost:8000` | frontend "falls back to the local backend" |

## 5. Recorded results

| Check | Date | Result |
| --- | --- | --- |
| Backend `pytest` on the files above | 2026-10-23 | 7 passed |
| Frontend `vitest` on the files above | 2026-10-23 | 53 passed |
| Local equivalent of CI, both halves (TC-P04) | 2026-10-23 | Backend: `ruff` clean, `compileall` ok, 1725 passed, 1 skipped (the opt-in DB test). Frontend: `oxlint` clean, `build` ok, 930 passed |

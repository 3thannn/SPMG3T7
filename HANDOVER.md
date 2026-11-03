# Handover: test traceability, test cut, defect fixes

Branch: `chore/playwright-test-reduction-handover`. Commit as
`3thannn <ethan.leong@gmail.com>`. Read this first; it supersedes
`HANDOVER_CLOUD_SESSION.md` for the testing work.

## The goal (from the team)

We had about 4,000 tests, too many to show that each one is needed and checks the right
thing. The aim is a defensible set: every Jira acceptance criterion (AC) has
test cases written the Week 4 way (happy path, one negative per rule,
boundaries), each tied to one automated test that someone has read. Plus an
**xlsx workbook laid out like the seniors' sheets** ("Created By / Date of
Creation / Executed By / Date of Execution" header block, then one plain row per
test case: Test Case ID, Test Scenario, User Story Reference, Pre-Conditions,
Test Steps, Test Data, Expected Result, Status). Simple, student-style wording.
Do not invent TDD dates or claim tests were written first unless they were
(only the D1–D8 fixes were truly test-first).

## Where things are

| File | What it is |
|---|---|
| `docs/testing/acceptance_criteria.yaml` | Every Jira story and AC, numbered `US4.7-AC2`; `kind` = behaviour / superseded / note / evidence / not built |
| `docs/testing/test_cases.txt` | **The source of truth: 488 test cases.** Format: `- id:` then `  key: value`, continuation lines indented 4 spaces. Fields: id, ac (comma list), category, scenario, preconditions, steps, data, expected, layer, test, why |
| `docs/testing/tools/tcparse.py` | Parser and validator: `python docs/testing/tools/tcparse.py docs/testing/test_cases.txt` |
| `docs/testing/tools/tcrefs.py` | Checks that every `test:` reference exists (backend AST, frontend titles incl. `it.each`, `evidence: path`) |
| `docs/testing/tools/tcgen.py` | Appends cases from pipe-separated rows (11 fields) |
| `docs/testing/tools/show.py` | Prints a test's source: `show.py tests/test_x.py::Class::test` or `pages/X.test.tsx::title` |
| `docs/testing/tools/prune_backend.py`, `prune_frontend.cjs`, `unused_frontend.cjs` | How the cut was done (remove every test not referenced in test_cases.txt; then remove unused helpers). Hooks are left alone. Re-run only with a keep list generated from the current test_cases.txt |
| `CODE_AUDIT.md` | What the code does; defects D1–D8 and their status |
| `REQUIREMENTS_BASELINE.md` | Customer rule changes vs Jira |
| `frontend/e2e-isolated/` | **All E2E now:** 38 browser journeys against `backend/e2e_server.py` (real API, in-memory stores, reset per test). `support.ts` has accounts and API set-up helpers. The old `e2e/` folder signed in to the live Supabase and was removed |

Test reference formats in test_cases.txt: `backend/tests/test_x.py::Class::test`,
`backend/integration/test_x_db.py::test`, `frontend/src/path.test.tsx::title`,
`frontend/e2e-isolated/x.spec.ts::title`, `evidence: README.md`.

## Current numbers (all green locally)

- Backend: 593 test runs (`pytest`), 6 DB suites (21 tests) on Postgres.
- Frontend: 66 Vitest tests; lint and `tsc -b` clean.
- E2E: 38 Playwright journeys (`npm run test:e2e`), in CI as job `e2e`.
- Coverage after the cut: backend about 78%, frontend about 50%. **CI gates still
  say 100% / 94%, so CI's coverage steps fail until task 1 below is done.**

## Defects fixed (test-first)

D1 stale safety approval, D4 misleading 404, D2 resubmit Rejected events, D3
Organiser controls registration, D7 cancel a Confirmed/flagged booking, D8
"No bookings were flagged" message. Each was checked against the Week 4
instructions and Week 7 changes before following the customer's answer. Details
and tests are in CODE_AUDIT.md section 4 and as `TC-D*` cases.

## What is left, in order

1. **Coverage: the "middle" option the user agreed to.** Restore the Supabase
   store contract tests (≈240 functions: classes named `*Supabase*`/`*Store*` and
   `tests/test_*_store.py`) from git history (commit `da67018` has the full suite),
   which takes the backend to ~86%. Add one load-error test per frontend page if
   cheap. Add each as a test case with `category: Technical`, and group them in
   the workbook ("Supabase booking store sends the right queries"). Then set
   `backend/pyproject.toml` `--cov-fail-under` and `frontend/vite.config.ts`
   thresholds to the reached level, and list what is not covered and why in the
   workbook (rubric: "100% unless not possible and stated why").
2. **The workbook** `docs/testing/build_workbook.py` → `docs/testing/ConnectSphere_Test_Cases.xlsx`
   (openpyxl). Sheets: one per epic or per role like the seniors (Unit/API,
   E2E), plus "Stories and ACs", "Defects fixed" (D1–D8), "Superseded rules",
   "Not covered and why". Read test_cases.txt with `tcparse.parse`, AC text
   from the YAML. Status column = Passed only if the test passed in a run you
   just did (run pytest/vitest/playwright with JSON reporters and match).
3. **Apply `backend/SUPABASE_FIX_ORGANISER_REGISTRATION.sql` to the live
   Supabase** (project `tlugwwgxiljuwytontqc`) **only after the user says yes**;
   until then an Organiser's registration save on production is refused (409).
   The DB is otherwise read-only unless the user asks.
4. Update `REQUIREMENTS_BASELINE.md` for D2/D3/D7/D8, then commit and push.

Notes:
- Minor, not fixed: an Organiser on an Under Review event sees "already been
  decided" when change requests are unavailable (they open once the Coordinator
  asks a question). Copy only.
- The team's `backend/tests/test_cases_*.md` docs cite tests that the cut
  removed; the workbook replaces them. Ask before deleting them.
- Opt-in DB tests (`tests/test_hold_expiry_db.py` and similar) ran against the live
  project and are gone after the cut. Keep it that way unless asked.

## How to run things

```bash
cd backend && python -m pytest -q
```

```bash
cd backend && TEST_POSTGRES_DSN=postgresql://postgres@localhost:5433/postgres python -m pytest -q --no-cov integration
```

```bash
cd frontend && npm run lint && npx tsc -b && npx vitest run --coverage
```

```bash
cd frontend && npm run test:e2e
```

E2E needs `backend/.venv` (a symlink to any venv with the backend requirements
works) and, when the container's Chromium doesn't match Playwright 1.64, set
`PW_CHROMIUM_PATH` to a Chromium binary (in the cloud container:
`/opt/pw-browsers/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell`).
A local Postgres for the DB suites: `initdb`/`pg_ctl` from `/usr/lib/postgresql/16/bin`, port 5433.

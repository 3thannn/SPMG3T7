# Handover: test traceability, test cut, defect fixes

Branch: `chore/playwright-test-reduction-handover`. Commit as
`3thannn <ethan.leong@gmail.com>`. Read this first; it supersedes
`HANDOVER_CLOUD_SESSION.md` for the testing work.

**Rule: update this file, commit and push it after every step you finish**, so
the next session can pick up mid-task. The repo now lives at
`github.com/3thannn/SPMG3T7`.

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
| `docs/testing/test_cases.txt` | **The source of truth: 498 test cases.** Format: `- id:` then `  key: value`, continuation lines indented 4 spaces. Fields: id, ac (comma list), category, scenario, preconditions, steps, data, expected, layer, test, why |
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

### Progress checkpoint — 4 November 2026

Step 1 complete: restored all eight standalone store files from `da67018`.
`ruff check tests` passes; `pytest --cov` reports **699 passed, 2 skipped,
82.64% combined line/branch coverage** on local Python 3.13. No restored test
needed D2/D3/D7 changes and no application code was changed. Installed the
declared requirements-dev dependencies in the existing local virtualenv.
Next: restore suitable embedded Supabase contract classes, then add grouped
Technical cases and regenerate all JUnit results/workbook. The numbers below
are the previous baseline until the final refresh. Live Supabase is off limits.

Step 2 complete: restored 15 embedded store classes from `da67018` in 14
files, with only their needed helpers/imports. `ruff check tests` passes;
`pytest --cov` reports **747 passed, 2 skipped, 85.66%**. All restored tests
passed against current application code without compatibility edits. This is
the requested roughly 86%; use 85.6 as the enforceable floor (do not round it
up above the real result). Next: add 10 grouped Technical cases, then run all
four JUnit suites and rebuild the workbook. Local PostgreSQL 16 installation
is in progress for disposable integration databases; never use live Supabase.

Step 3 complete: generated TC-STORE-01 through TC-STORE-10 with `tcgen.py`.
There are now **498 cases**, including ten grouped Technical adapter cases.
`tcparse.py` reports no missing fields and `tcrefs.py` no missing references.
Each group has one representative test and plain wording explaining the other
checks for that adapter. Next: raise the floor to 85.6%, regenerate the four
JUnit reports, rebuild the workbook and publish the same tree to both branches.

Step 4 complete: all four fresh JUnit runs passed on 4 November 2026. Backend
coverage is **85.66% combined line/branch (88.38% lines)**; floor raised to
**85.6%**. Workbook regenerated from `/private/tmp/spmg-final-results` using
the existing builder and checked against the parsed cases and a rendered preview.
Frontend coverage: 52.76% lines, 51.30% statements, 49.20% functions, 48.89%
branches. Backend Ruff/compileall and frontend lint/build pass (two existing
React effect warnings, no lint errors). All coverage gates pass.

Closed one existing traceability omission without adding a test: TC-E2E-28
already asserts the Organiser confirmation notice, so it now also names
US4.7-AC5 (the same rule as US10.3-AC2). All 214 behaviour ACs have a case.
The ten Technical cases group adapter contracts; they do not claim a live
Supabase end-to-end check. No application code or live database was changed.
DB integration used a disposable local PostgreSQL 16 cluster on port 5433,
which was stopped afterwards. No Docker needed.

Publish this checkpoint to the working branch and the identical tree to
`final-amendments-after-audit`, with its current remote tip as parent (no force).
Done: both branches held the same tree.

Step 5 (4 November 2026): removed `backend/SUPABASE_FOUR_STORY_FIX.sql`. It came
in with `98b65e8` ("prepare test reduction handover"), nothing referenced it,
and its header said to run the whole file in the SQL Editor. It holds older
copies of functions that later scripts replaced, so running it would undo two
stories: its `reassign_event_coordinator` lets a Lead reassign Completed,
Cancelled or Rejected events again (US8.4 refuses them, see
`SUPABASE_US8_4_REASSIGN_COORDINATOR.sql`), and its
`flag_bookings_for_unavailability` stops telling Organisers about a venue
closure (US12.4, `SUPABASE_US12_4_REOPEN_FOR_REPLACEMENT.sql`). Every change it
makes is covered by the per-story scripts in the README's table. No application
code, test or live database changed. Re-checked locally on this tree: backend
`ruff check` and `pytest --cov` (747 passed, 85.66%), frontend lint, `tsc -b`,
build and Vitest coverage (66 passed, every floor met), and the 38 Playwright
journeys. The DB suites were not run locally (no PostgreSQL on that machine);
CI runs them.

Remaining user actions: open the PR from `final-amendments-after-audit` into
`main`, wait for GitHub checks (CI runs only on pull requests and on `main`, so
the PR is the first CI run of this tree), get the team's agreement (it deletes
the cut tests, about 32,700 lines), use Squash and merge, and decide whether to
delete the old `backend/tests/test_cases_*.md` docs. SPMG3T7-91 is already
gone (see the Jira section).

- Backend: 747 passed, 2 skipped (`pytest --cov`, floor 85.6% in `backend/pyproject.toml`).
- DB suites: 20 tests on Postgres (`integration/`).
- Frontend: 66 Vitest tests, floors in `frontend/vite.config.ts` (lines 52 / statements 51 / functions 49 / branches 48); lint, `tsc -b` and build clean.
- E2E: 38 Playwright journeys (`npm run test:e2e`), CI job `e2e`.
- Workbook: `docs/testing/ConnectSphere_Test_Cases.xlsx`, built by
  `docs/testing/build_workbook.py <junit-results-dir>` (see its docstring for
  the four JUnit runs). 498 cases: 491 Passed, 5 Evidence, 2 Not Executed
  (opt-in DB tests: `tests/test_hold_expiry_db.py` needs the live project,
  `tests/test_equipment_reservations_db.py` needs a database with every
  migration applied). Layout follows the seniors' sheets.

## Defects fixed (test-first)

D1 stale safety approval, D4 misleading 404, D2 resubmit Rejected events, D3
Organiser controls registration, D7 cancel a Confirmed/flagged booking, D8
"No bookings were flagged" message. Each was checked against the Week 4
instructions and Week 7 changes before following the customer's answer. Details
and tests are in CODE_AUDIT.md section 4 and as `TC-D*` cases.

## Branches

- `chore/playwright-test-reduction-handover`: the working branch with checkpoint commits.
- `final-amendments-after-audit`: the same tree, published as a new commit on
  its existing tip. Open the PR from this one into `main`. The user
  will delete the old branch themselves (history rewrites are blocked here).

## Jira (done)

Stories amended to match the code: SPMG3T7-38 (US4.3, resubmit Rejected),
-79 (US20.1, Organiser controls registration), -58 (US14.2, cancel Confirmed or
flagged bookings), -86 (US11.3, important change during the safety check).
SPMG3T7-91 was created by mistake and has been deleted: on 4 November 2026 Jira
answered "not found" for it while SPMG3T7-86 still loaded. Do not create new
Jira issues.

## Completed task (user approved; kept for audit)

**Goal: raise backend coverage while keeping the test count small enough for
the team to review every test.** Add back the Supabase store contract tests,
listed in the workbook as about 10 grouped "Technical" test cases (one per
store), not one row per test.

1. Restore the standalone store test files from before the cut:

   ```bash
   for f in test_booking_store test_equipment_store test_notification_store test_registration_store test_user_store test_venue_store test_venue_unavailability_store test_draft_store; do git show da67018:backend/tests/$f.py > backend/tests/$f.py; done
   ```

   (`test_booking_store.py` and `test_venue_store.py` still exist with their
   tests removed, because other tests import their helpers; overwriting them
   keeps those helpers.) Then run `ruff check tests` and `pytest --cov`. Fix
   anything that no longer matches the code (D2/D3/D7 changed
   `registration_store.set_settings`, `booking_store.cancel` and
   `event_store.submit_event`).
2. Optionally also restore the `TestSupabaseStore`-style classes inside other
   files (they are in `da67018`), for about 240 functions in total and about 86%
   coverage.
3. Add one `category: Technical` test case per store to
   `docs/testing/test_cases.txt` (layer `Unit`, test = one representative test
   from that file, why = "the production store sends the right queries; the
   rest of this file's tests check the same adapter").
4. Raise `fail_under` in `backend/pyproject.toml` to the new total, re-run the
   four JUnit runs (see `build_workbook.py`), rebuild the workbook, update the
   Summary sheet's coverage line, commit as 3thannn and push to **both**
   branches (rebuild the single commit on `final-amendments-after-audit`
   with `git commit-tree "HEAD^{tree}" -p <current-remote-tip>` then push it;
   never use the old base as parent or force-push).

Do not delete defensive error handling to raise coverage; the user agreed to
keep it.

Notes:
- Minor, not fixed: an Organiser on an Under Review event sees "already been
  decided" when change requests are unavailable (they open once the Coordinator
  asks a question). Copy only.
- The team's `backend/tests/test_cases_*.md` docs cite tests that the cut
  removed; the workbook replaces them. Ask before deleting them.

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

# Test suite audit

Measured on 2026-11-03 against `main` at `a6c8213`. Every number comes from a
command run in this repository. Regenerate the CSVs with
`backend/generate_test_inventory.py`.

## 1. Result

| Layer | `main` | This branch |
| --- | ---: | ---: |
| Backend (pytest) | 2,513 passed, 10 skipped | **1,557 passed, 10 skipped** |
| Backend coverage (line + branch) | 100% | **100.00%** |
| Frontend (Vitest) | 1,406 passed | 1,406 passed (unchanged) |
| Browser (Playwright) | 43 (33 shared/live, 10 isolated) | 43 |

The backend lost 956 tests (38%) and kept 100% coverage, which the course
rubric asks for ("100% coverage unless not possible and stated why").

The seniors' example scripts you shared have about 100 unit rows and 40-100 E2E
rows per role. This suite is larger on purpose: the Project Instructions grade
"comprehensive and traceable" testing with normal, boundary, conflict and failure
cases, and it says instructors may ask you to trace a requirement to its tests.

## 2. How the backend was cut

The cut started from `main`'s complete suite, not from the earlier trimmed
branch, whose truncated files had lost assertions and coverage. A test is kept if
any of these hold. They are applied in order by `select_minimal_tests.py`.

| Why it is kept | Cases |
| --- | ---: |
| A test-case document cites it (traceability) | 770 |
| It is a real-database test (`integration/`, `*_db.py`) | protected, run opt-in |
| It sits in a small file that proves a rule the customer set or changed | 148 |
| It is needed so every line and branch arc stays covered (measured per test) | 552 |
| It is the best test of a class or file that would otherwise vanish | 87 |
| **Total** | **1,557** |

"Customer-changed rule" files cover Lead assignment and the unassigned queue,
hold expiry, replacement venues, reconfirmation after a change, and Safety
approval followed by the Coordinator's own confirmation (US4.7). Coverage alone
dropped these, because other tests touch the same lines. For example, the three
tests that prove "approval no longer confirms the event" were cut by the
coverage rule and are kept by this one.

Only whole test functions were removed. Helpers, fixtures and the real-database
tests were not touched. `apply_test_selection.py` makes the removal, and
`ruff check --fix` clears the imports that nothing uses afterwards.

## 3. Repairs made along the way

| Problem | State |
| --- | --- |
| The earlier trimming removed `FakeAdmin` but one test still imported it | Fixed |
| Four tests had lost every assertion and checked nothing | Fixed |
| About 109 lint errors and 4 unused variables left by the trimming | Fixed |
| Coverage had fallen to 90.05% | Fixed (100.00%) |
| 161 test cases cited tests the trimming had deleted | Fixed (all 612 cited names exist) |
| TC-S06 said Safety approval confirms the event, which US4.7 replaced | Fixed |

## 4. What is not cut, and why

- **Frontend.** Vitest cannot record which test covers which line, so the
  backend method does not carry over. The eight coverage-scaffold files were
  tried one at a time and kept unless removing them kept every threshold
  (100% lines, statements and functions; 94% branches). Result: all eight were needed. Removing any one dropped line
  coverage to between 98.3% and 99.8%, below the 100% threshold, so none was removed.
- **Parametrized tests.** A kept test keeps all its cases. Seventeen functions
  expand to six or more cases (138 in total). Trimming them to one case per
  equivalence class needs a person to choose which cases represent which class.
- **Browser tests.** None of the 43 is cited by a test case yet. They are
  few, and the seniors' E2E suites are comparable in size.

## 5. What has and has not been verified

Coverage tells you which lines ran. It does not tell you a test checks the right
thing, which matters most for tests an AI wrote. So:

- **Checked by script:** all but two kept backend tests assert directly in their
  own body (`Assertions In Test` column in `test_inventory.csv`). The two
  exceptions, in `test_attendee_notices_us10_4.py`, assert through the
  `change_and_accept` helper, which checks both calls return 200. The docs cite no test
  that does not exist (612 of 612 backend names found), and the full suite meets
  the 100% gate.
- **Not checked by anyone yet:** that each kept test asserts the *correct* result.
  That is a human job. `test_inventory.csv` and `test_case_register.csv` carry
  blank `Reviewed By` and `Review Result` columns for named team members. Nothing
  in this repository counts as a review.
- **How a reviewer can use the CSVs:** `Why Kept` says why a test survived, and
  `Test Case ID` and `Acceptance Criteria` say which documented behaviour it is
  meant to prove. Read the test and the test case side by side and mark the row.
- **Known wording drift:** 11 frontend test titles cited in the docs do not match
  any test title exactly (some are truncated or worded differently). The tests are
  there; the citations need tidying.
- **No new tests were written** in this reduction. Four tests that an earlier
  trimming had gutted were restored from `main`.

## 6. Not covered by this audit

- Whether any test was written before its code (TDD). Only the git history can
  show that, and this clone is shallow.
- Human review. The `Reviewer` and `Review result` fields are for named team
  members; nothing here counts as a review.
- The Postgres migration tests, which need `TEST_POSTGRES_DSN` and were not run.

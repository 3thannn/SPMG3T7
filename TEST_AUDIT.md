# Test suite audit

Measured on 2026-11-03. Every number below comes from a command run in this
repository, not from the older handover notes. Regenerate the CSVs with
`backend/generate_test_inventory.py`.

## 1. Where we are

| Layer | `main` | This branch |
| --- | ---: | ---: |
| Backend (pytest) | 2,505 passed, 10 skipped | 1,534 passed, 10 skipped |
| Backend coverage (line + branch) | **100%** | **90.05%** (CI gate is 100%) |
| Frontend (Vitest) | 1,400 passed in 65 files | 1,400 passed in 65 files |
| Browser (Playwright) | 43 (33 shared/live, 10 isolated) | 43 |

The seniors' example scripts you shared are far smaller than this. Their unit
scripts have about 100 rows each and their E2E scripts 40-100 rows per role.
We are running roughly 3,000 automated tests.

## 2. What the earlier trimming did

The 971 backend tests removed from `main` came out of 27 test files (8,749 lines
deleted). Verified side effects, now corrected unless marked open:

| Problem | State |
| --- | --- |
| `FakeAdmin` and two helper classes removed but still imported, so 1 test failed | **Fixed** (restored from `main`) |
| 4 tests lost every assertion and passed while checking nothing | **Fixed** (bodies restored from `main`) |
| 109 auto-fixable lint errors (mostly unused imports) and 4 unused variables left behind, so `ruff check` failed in CI | **Fixed** |
| 161 test-case entries in `backend/tests/test_cases_*.md` cite tests that were deleted | **Open** (listed in `test_case_register.csv`) |
| Backend coverage fell from 100% to 90.05%; about 485 production statements are now untested | **Open** |

Lesson for any further cutting: do not truncate files. Remove whole tests,
one feature at a time, and run the coverage check after each batch.

## 3. What can be cut mechanically, and what cannot

Rules that need no judgement about behaviour (flagged in the `Audit Flag`
column of `test_inventory.csv`):

| Rule | Tests | Realistic saving |
| --- | ---: | ---: |
| Coverage-scaffold files (`*.paths.test.tsx`, `*.calls.test.ts`, `App.routes.test.tsx`) to fold into their owning feature tests | 100 | about 60-100 |
| Single tests that expand to 6+ cases (17 functions, 138 cases) | 138 | about 85 (keep one case per equivalence class) |
| **Total mechanical** | | **about 150-190 (5-7%)** |

Getting to the 610-690 target in `handover.md` is a different kind of work:

- 2,090 of 2,729 listed tests are not cited by any test case in the documents:
  2,047 backend and frontend tests, plus all 43 browser tests. That does not
  mean they are useless; it means nobody has yet said which acceptance
  criterion each one protects.
- Only 14 of the 24 test-case documents have an AC table in the `| ACn |` format
  (85 ACs between them).
  Sizing by ACs needs the other documents' criteria written down first.
- Each cut lowers coverage unless the production code it covered is also
  covered elsewhere. `main`'s 100% gate means every cut has to be checked.

## 4. Options

| Option | What it means | Risk |
| --- | --- | --- |
| A. Repair this branch, then cut | Restore enough tests to return to 100%, then apply the mechanical rules | Keeps more tests than the target |
| B. Restart from `main` | Cut AC by AC using `test_inventory.csv`, keeping 100% or an agreed lower gate | More work, but each cut is reviewable |
| C. Keep the suite, curate the demo | Leave CI as is; build a 100-150 case script set in the class template for the presentation | The suite stays large |

My recommendation is B for the suite and C for the presentation. The
decision about whether the 100% coverage gate can drop belongs to the team.
`handover.md` says not to lower it silently.

## 5. Not covered by this audit

- Whether any test was written before its code (TDD). Only the git history can
  show that, and this clone is shallow.
- Human review. The `Reviewer` and `Review result` fields are for named team
  members; nothing here counts as a review.
- The Postgres migration tests, which need `TEST_POSTGRES_DSN` and were not
  run here.

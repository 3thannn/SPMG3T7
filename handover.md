# ConnectSphere test-reduction handover

## Mission for Claude

Reduce the automated suite from roughly 4,000 configured cases to a set that a five-person student team can independently read, run, explain and sign off. The working target is **610–690 automated cases**, with about **660** as the planning number.

This is a controlled reduction, not a rewrite and not a coverage-number exercise. Preserve distinct customer behaviour, current acceptance criteria, important permission boundaries, transaction/race risks and production SQL integration. Delete or consolidate repeated examples, coverage-only permutations, repeated mock plumbing and tests of superseded requirements.

Do not claim that a test was human-reviewed. Produce a review register for the team to initial themselves.

## Starting point

- Branch: `chore/playwright-test-reduction-handover`
- Base pulled from `main`: `9770290`
- The branch contains the previously uncommitted credential/documentation/test-plan work, both audit reports, and the Playwright repair described below.
- No bulk test reduction has been performed yet.
- Read these first:
  - `TEST_SUITE_US_AC_AUDIT.md` — primary reduction plan, per-suite counts, AC conflicts and proposed targets.
  - `CONNECTSPHERE_AUDIT_REPORT.md` — implementation/requirements audit and remaining product risks.
  - `INDEPENDENT_TEST_REDUCTION_AUDIT.md` — independent second opinion; reconcile it with the repository rather than accepting it blindly.
  - `MASTER_TEST_PLAN.md` and `test-plans/` — current manual story allocation and review material.

Measured baseline on 3 November 2026:

| Layer | Baseline |
|---|---:|
| Backend pytest | 2,512 collected; 2,504 passed and 10 skipped |
| Frontend Vitest | 1,400 passed across 65 files |
| Playwright | 43 configured: 33 shared/live and 10 isolated |
| CI Postgres integration | 28 named functions across four modules |
| Total | At least 3,983 configured cases/functions |

Backend coverage measured 100% statements and branches. Frontend measured 100% statements/lines/functions and 94.81% branches. Coverage is evidence, not a reason to retain duplicate tests.

## Playwright repair already completed

The isolated E2E harness is working before reduction begins:

- `backend/e2e_server.py` now converts the pytest fixture users to the documented `@connectsphere.com` browser accounts and uses password `password`. It does not mutate the ordinary pytest account fixtures.
- `frontend/e2e-isolated/safety-check-us17.spec.ts` now tests the current US4.7 rule: Safety approval does not auto-confirm; the assigned Coordinator confirms separately.
- `frontend/e2e-isolated/venue-delete-us9-5.spec.ts` uses the current Venue Staff account.
- Verification: `npm run test:e2e:isolated` → **10 passed**.

Do not regress this harness or change it back to `@spmg3t7.edu` / `Sprint1!demo`.

## Target shape

| Layer | Target |
|---|---:|
| Backend feature/API | 350–390 |
| Backend essential store + real database integration | 40–50 |
| Frontend Vitest | 200–230 |
| Isolated Playwright | 20 eventual scenarios, one per baseline E2E journey |
| Total | 610–690 |

Treat the range as a guardrail, not a quota. A case stays only when the team can name the current AC or concrete failure risk that it uniquely proves.

## Non-negotiable retained behaviour

Retain representative positive, refusal and boundary coverage for:

1. Authentication and every role/assignment permission boundary.
2. Draft, submission, review, clarification, approval/rejection and cancellation transitions.
3. US4.7: current Safety approval followed by assigned-Coordinator confirmation.
4. US8.4: active-event reassignment, access transfer, both notices, audit names and stale/atomic failure.
5. US11.3: accepted important Confirmed-event change reopens Planning, rechecks arrangements, requires fresh Safety approval and reconfirmation.
6. US12.4/US14.5: venue problem, Coordinator replacement action, Planning reflow and preservation of unaffected bookings.
7. Venue conflict/turnaround/operating-hours rules and concurrent booking protection.
8. Equipment availability/reservation conflicts and role decisions.
9. Registration capacity, duplicate registration, withdrawal and attendee privacy.
10. Notification recipient isolation and read state for material lifecycle actions.
11. Real Postgres RPC/migration behaviour for the four CI integration modules.
12. The ten currently green isolated browser tests.

Do not preserve tests that expect Safety approval to auto-confirm. Do not restore superseded round-robin assignment or “any Coordinator can manage any event” behaviour. The audit explains all known AC precedence conflicts.

## Controlled execution order

### 1. Build a machine-readable inventory

Before deleting anything, create a CSV or Markdown review register with at least:

`test ID/path | layer | current AC/risk | unique behaviour | proposed action | replacement test | reviewer | review result`

Populate proposed actions with `keep`, `merge`, `delete-superseded`, or `delete-duplicate`. Leave reviewer/result blank for humans.

Use pytest collection and Vitest JSON output to refresh the audit counts. Do not estimate when the runner can report an exact number.

### 2. Remove the clearest scaffolding first

- Consolidate backend coverage/guard files into their owning feature suites.
- Consolidate frontend `*.paths.test.*`, `*.calls.test.*` and route-coverage permutations.
- Preserve a behaviour when removing its coverage scaffold; move one clear assertion into the owning test if necessary.
- Run the relevant focused suite after every file or small batch.

### 3. Reduce backend feature suites by equivalence class

Start with the largest files listed in `TEST_SUITE_US_AC_AUDIT.md`: change requests, venue unavailability, registration, Safety checks, cancellation, turnaround, event needs, conflicts, holds and venue bookings.

For each rule normally keep:

- one happy path;
- one authorization/ownership refusal where the boundary is not already covered centrally;
- one validation equivalence class per distinct rule, not one per spelling/value;
- one status-transition refusal;
- one boundary/race/atomicity case where relevant;
- one notification/audit assertion at the layer that owns it.

Merge parameter rows that prove the same branch. Prefer one readable scenario over many tiny tests that repeat setup and mocks.

### 4. Reduce frontend tests around visible states

Prioritise `EventBookings`, `venuesStore`, `status`, `SafetyCheckPanel`, `EventChangeRequest`, permissions, venue unavailability/form, `EventDetailPage`, `eventsStore`, turnaround, registration, draft rules and event needs.

Keep customer-visible rendering, enabled/disabled decisions, request shape, error translation and meaningful state transitions. Delete repeated fetch call-order, empty/null permutations and prop combinations already proved below the component.

### 5. Preserve integration and browser confidence

- Do not replace Postgres integration cases with mocks.
- Do not run shared/live Playwright against Supabase when destructive data or credentials are not controlled.
- Keep the isolated suite green throughout.
- After unit reduction, map baseline E2E-1…20 to one isolated journey each. Add only genuinely missing journeys; do not multiply browser variants.

### 6. Reconcile thresholds honestly

Do not silently lower coverage thresholds merely to make CI pass. First consolidate while retaining the existing thresholds. If a useful reduction makes 100% backend branch coverage unreasonable, record the exact uncovered production lines and proposed threshold change for team approval. Coverage should never substitute for AC traceability.

### 7. Commit in reviewable batches

Use small commits grouped by feature or test layer, for example:

- `test: consolidate backend change-request coverage`
- `test: reduce duplicate venue lifecycle cases`
- `test: consolidate frontend path and store tests`
- `docs: add retained-test review register`

Every commit message/body should state the before/after case count and the focused/full checks run. Never combine a product behaviour change with bulk test deletion.

## Validation gates

Use Python 3.12, matching CI. The checked-in local backend virtual environment may be Python 3.13 and previously lacked some CI packages, so rebuild it if necessary rather than changing requirements to suit the local machine.

```sh
cd backend
ruff check .
python -m compileall -q app
pytest --cov
TEST_POSTGRES_DSN=postgresql://postgres:postgres@localhost:5432/postgres \
  pytest integration/test_unavailability_db.py integration/test_change_review_db.py \
  integration/test_us12_4_db.py integration/test_us8_4_db.py

cd ../frontend
npm run lint
npm run build
npm test -- --coverage
npm run test:e2e:isolated
```

The Postgres command requires a clean PostgreSQL 16 database. The isolated Playwright command starts local servers on ports 8001 and 5174.

At the end of every reduction phase, record:

- exact collected/passed/skipped counts by layer;
- coverage delta;
- deleted and merged tests with their replacement location;
- any AC whose coverage became manual-only;
- commands and results;
- human reviewers still required.

## Known issues outside the reduction scope

Do not quietly fix these while deleting tests; keep them visible for a separate product-change commit:

- Direct Coordinator edits of Confirmed event fields are still accepted; they should go through the reviewed important-change/reconfirmation flow.
- Venue Staff can set hold expiry but cannot update it.
- Safety review lacks explicit emergency-access, equipment-placement and crowd-movement inputs.
- Venue-hours interpretation for the initial request and buffered setup/turnaround remains open.
- C4 diagrams and a real repository URL are missing.
- `backend/SUPABASE_FOUR_STORY_FIX.sql` is an untracked-era omnibus repair bundle now committed on this branch for preservation; the focused migrations on `main` appear to supersede it. Do not apply or merge it into the migration order without comparing every function and obtaining team approval. Prefer deleting it in a dedicated reviewed commit once confirmed obsolete.

## Definition of done

The reduction is complete only when:

- 610–690 meaningful automated cases remain, or a documented reason justifies a nearby count;
- every retained test maps to a current AC or named technical risk;
- every deletion/merge has an auditable entry;
- superseded ACs are clearly marked;
- backend, frontend, Postgres integration and isolated E2E commands are reproducible;
- coverage is reported honestly;
- the review register is ready for five named team members to inspect and initial;
- no document claims that AI review counts as independent human review.

The desired final explanation to the professor is: “We retained a reviewable set of tests, each tied to a current acceptance criterion or a concrete failure risk, and every retained test was independently reviewed by a named team member.”

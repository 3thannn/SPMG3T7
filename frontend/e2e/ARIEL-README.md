# Ariel's live Playwright regression tests

These tests follow the real-login approach in `authentication.spec.ts` and
`coordinator-lead-assignment.spec.ts`. They use the running FastAPI backend and
its existing Supabase project. No API mocks, reset endpoints or new project.

Start the test-only wrapper from `backend` with:

```powershell
.venv\Scripts\python.exe -m uvicorn --app-dir ../frontend/e2e e2e_backend:app --host 127.0.0.1 --port 8000
```

Then run from `frontend`:

```powershell
$env:E2E_ALLOW_SHARED_WRITES='1'
npm run test:e2e -- ariel- change-review-us11-2 --workers=1 --reporter=line
```

Playwright starts Vite. Use one worker to limit load on the shared database.
Demo accounts required: organiser, coordinator, coordinatorlead, venuestaff,
technicalsupport and safetyofficer at `@spmg3t7.edu`. Default password follows
the existing helpers; override with `E2E_PASSWORD` if all demo accounts use a
different password. `E2E_API_URL` overrides fixture requests; set
`VITE_API_BASE_URL` to the same URL when starting Vite. Existing database
migrations must already be applied. Missing migrations/accounts cause failures;
the suite does not apply migrations or change account credentials.

The wrapper adds only a test-process identity endpoint; production API/UI files
are unchanged. Before any test writes and before every cleanup, a fresh random
challenge proves the API's actual cached admin client has the same Supabase URL
and service key as the cleanup process. Keys and project URLs are never returned
by the endpoint. A missing endpoint, failed proof, timeout or redirect stops the
run; cleanup cannot mark its manifest cleaned on a mismatch. Override backends
must run this wrapper too, using the same Supabase configuration as local cleanup.
Browser fetch/XHR requests to an address other than the verified API are blocked
before dispatch, protecting against an inconsistent `VITE_API_BASE_URL`.

| Jira ticket | Spec | Coverage |
| --- | --- | --- |
| SPMG3T7-27 / US3.1 | ariel-events | Own event list/detail, persisted edits, submitted read-only form |
| SPMG3T7-29 / US4.2 | ariel-events | Draft save, submit once, actor/time audit |
| SPMG3T7-35 / US7.1 | ariel-events | Approval/rejection, required reason, Organiser visibility |
| SPMG3T7-38 / US4.3 | ariel-events | Review transitions, repeat decision refusal |
| SPMG3T7-39 / US9.1a | ariel-catalogues | Venue create/validation, Coordinator write refusal |
| SPMG3T7-60 / US4.5 | ariel-events | Lead assignment, first booking, safety-gated completion, elapsed end time |
| SPMG3T7-63 / US19.1 | ariel-catalogues | Stock create/edit, maintenance reason, usable quantity, role restrictions |
| SPMG3T7-64 / US19.0 | ariel-catalogues | Read-only check of existing varied sample stock; never reruns the seed script |
| SPMG3T7-65 / US19.2 | ariel-equipment | Exact catalogue item, default times, edit/remove, support queue and notes |
| SPMG3T7-77 / US19.3 | ariel-equipment | 10 total minus 2 maintenance minus 6 reserved, shortfall, reason, notification |
| SPMG3T7-78 / US11.2 | change-review-us11-2 | Real clarification/amendment, accept/reject, persisted venue conflict, status preserved, notification |

## Shared data and compatibility

Live writes require explicit `E2E_ALLOW_SHARED_WRITES=1`. Each test checks admin
cleanup access and refuses to write while any earlier Ariel E2E records remain,
then uses an unpredictable run prefix and tracks
its exact record IDs. After every test, `cleanup-data.py` backs up its records,
checks for references from non-test data, and hard-deletes only this run's data
in dependency order. Completed events, soft-deleted requests, audit history,
notices, bookings, venues and equipment are removed rather than left in the UI.
No schema changes or new cleanup API routes are needed. Cleanup failure fails
the test; HTTP 409 is no longer accepted as a successful cleanup.

The helper uses the backend Python environment, existing `backend/.env` and
Supabase admin client. Set `E2E_PYTHON` if that interpreter lives elsewhere.
Credentials stay server-side and never enter the browser. Test catalogues can
be visible temporarily while an explicitly opted-in run is active; they must
be absent afterward. No shared sample stock or notification read states change.

Persistent recovery manifests are stored in `frontend/playwright/.cache/recovery`
before the first write, and local backups in `frontend/playwright/.cache/cleanup`.
Both directories are gitignored. If a run is interrupted, use the exact prefix
from its manifest (first inventory, then cleanup) from the repo root:

```powershell
backend\.venv\Scripts\python.exe frontend/e2e/cleanup-data.py --prefix Ariel-E2E-<timestamp>-<suffix> --verify-api http://localhost:8000
backend\.venv\Scripts\python.exe frontend/e2e/cleanup-data.py --prefix Ariel-E2E-<timestamp>-<suffix> --verify-api http://localhost:8000 --apply
```

Use the API URL saved in the recovery manifest if it differs from localhost.
`--apply` requires API verification even for manual recovery. A final read-only
local-database check for leftovers from any of these runs is:

```powershell
backend\.venv\Scripts\python.exe frontend/e2e/cleanup-data.py --prefix Ariel-E2E- --check
backend\.venv\Scripts\python.exe frontend/e2e/test_cleanup_data.py
```

The original retained data was backed up and removed: 28 venues, 11 equipment
items, 34 events and 485 dependent rows, including 210 notifications. The cleanup
verified that every pre-existing non-test row in the checked application tables
was unchanged. The HTTP/1.1 and event-load retry troubleshooting fixes remain.

Tests honor US2.1's updated mandatory needs, US8.2/8.3/8.6's manual Lead assignment
and Coordinator isolation, and US4.4/17.2's safety approval. Old auto-assignment
and any-Coordinator access rules are not asserted. CI and the disabled replacement
venue specs are unchanged. Equipment removal is a soft delete: the test expects
the row to remain as Removed history with no edit/remove controls.

These are workflow regressions, not exhaustive acceptance coverage. The existing
database has only one Organiser account, so cross-Organiser ownership isolation
needs an additional account before it can be exercised. US11.2 currently exercises
venue suitability flags; equipment rechecks and direct Coordinator edit conflicts
remain covered by the existing lower-level tests.

## Validation and resolved issues

After the shared database review scripts were reapplied, all four live cases in
`ariel-equipment.spec.ts` and `change-review-us11-2.spec.ts` passed together
(3.5 minutes): request/edit/remove with support notes, overlapping equipment
reservations, clarification/amendment/acceptance with persisted venue flags,
and rejection with preserved values and a visible reason.

The backend's default shared HTTP/2 connection had returned intermittent
`httpx.RemoteProtocolError: Server disconnected` errors during concurrent page
reads. Admin database calls now use pooled HTTP/1.1 connections, retaining the
existing timeout and authentication isolation. Writes are not automatically
retried. Resetting the client closes its transport. The event detail page now
shows a load error and a Retry loading event button instead of remaining stuck
on Loading event after a rejected fetch.

Validation also passed: 12 Supabase configuration/transport tests, 285 equipment
and change-review backend tests, 104 focused frontend tests, frontend build,
lint (existing TeamAssignments warnings), and the E2E TypeScript check. All 11
existing authentication cases passed during the earlier compatibility run.

The earlier PostgreSQL 42702 error, `column reference "c" is ambiguous`, stopped
occurring after the user applied `SUPABASE_US11_2_CHANGE_REVIEW.sql` followed by
`SUPABASE_US11_2_REVIEW_FIXES.sql`. No additional schema changes were needed.

## Cleanup validation

The full 11-case suite was exercised: nine passed initially; one cleanup TLS
reset and one application request connection failure were recovered, and both
affected cases passed on rerun. Cleanup reads and exact-ID deletes now have
bounded retries; application submissions are never automatically replayed.
Eight offline cleanup safety tests, E2E TypeScript checking and lint passed.
A final global check found zero Ariel E2E records in all 14 checked application
tables and verified that every original non-test row still matched the initial
backup. Refresh an already-open app page to reload its catalogue and notices.

Database-target regression checks: all 15 offline safety tests passed, including
a different project, different key, missing endpoint, timeout, replayed proof
and manual deletion without verification. A live matching-configuration check
passed; an intentionally mismatched project was rejected before inventory. The
read-only US19.0 browser smoke test passed against the wrapper and left zero
test records. These checks did not create venue, equipment or event records.

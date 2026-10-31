# Ariel's live Playwright regression tests

These tests follow the real-login approach in `authentication.spec.ts` and
`coordinator-lead-assignment.spec.ts`. They use the running FastAPI backend and
its existing Supabase project. No API mocks, reset endpoints or new project.

Start the backend from `backend` with `.venv\Scripts\python.exe -m uvicorn
app.main:app --host 127.0.0.1 --port 8000`, then run from `frontend`:

```powershell
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

Each test creates `Ariel-E2E-<time>-<random>` records and tracks their exact IDs.
Teardown cancels its active events, releasing their bookings/reservations, and
attempts to delete only its venues/equipment. A 409 means audit history retains
the catalogue record; the test prints its ID. Cancelled/completed/rejected events
and their notices/history remain intentionally. These records can appear in demo
lists. Completed events are immutable and retain their booking on a uniquely
created test venue, which is never reused by another test. No shared sample records, account names, or notification read states are
changed. Interrupted runs may require manual cancellation of the printed test
event; never reset the shared database.

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

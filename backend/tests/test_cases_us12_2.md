# US12.2 approval and test-scope audit

Scope source: PR #42's user story and acceptance criteria. No separate approved
US/AC document was present in the repository. This mapping does not claim to
replace a course/project requirements specification.

## Acceptance coverage

| Requirement | Evidence |
| --- | --- |
| Venue Staff record structured reasons; Other requires text | Existing API validation/permission tests in test_venue_unavailability.py and form/store tests |
| Flag Requested, unexpired Held and Confirmed bookings | integration/test_unavailability_db.py::test_active_bookings_flagged_once_and_decisions_preserved |
| Leave Cancelled, Rejected, Expired, expired Held, other venues and non-overlapping bookings alone | Same integration scenario, with explicit unchanged-row assertions |
| Include setup/turnaround; touching boundaries do not overlap | test_setup_turnaround_overlap_excludes_exact_midnight_boundaries |
| Notify the assigned coordinator once per affected event | Active-bookings scenario: two assigned events, multiple bookings, unassigned event and repeated blackout |
| Preserve confirmed decision metadata | Active-bookings scenario checks decided_at and decided_by_id after flagging |
| Reason reaches affected bookings and notifications | test_reason_reaches_booking_and_notification (four reason variants); maintenance covered in active-bookings scenario |
| API exposes replacement details | test_venue_bookings.py::TestRequestingABooking::test_flagged_booking_exposes_replacement_details |
| UI shows reason and actionable guidance | EventBookings.test.tsx replacement-notice test |
| Form offers five reasons and reports affected count | Existing VenueUnavailability.test.tsx form and success-message scenarios, strengthened rather than duplicated |
| Existing data survives deployment and migration reruns | test_migration_preserves_legacy_reasons_and_is_rerunnable |

## Removed and consolidated

- Three overlapping migration scripts become one rerunnable migration. The
  status-only partial index is unnecessary for the actual count query, which
  uses flagged_by_unavailability_id and retains its index.
- The manual SQL script is removed: it printed expected results rather than
  asserting them, used fixed shared IDs, omitted coordinator assignment, and
  contradicted itself about exact-midnight overlap.
- Five data-dependent Playwright cases are removed. The first three duplicated
  form/component coverage; the last two could pass without any assertion.
  They are replaced by isolated PostgreSQL, API-contract and UI-component
  checks, not represented as end-to-end browser coverage.
- The two single-use SQL overlap helper functions are no longer created on
  fresh installs; their simple arithmetic is in the trigger. Existing deployed
  helpers are left alone to avoid deleting unknown dependencies.

## Keep rather than prune

The large venue-unavailability API/store/form suites mostly predate US12.2 and
protect US12.1: authorisation, date validation, planning filters, ordering,
loading/error handling and persistence. They are shared regression coverage,
not all separate US12.2 acceptance test cases. Do not delete them merely to
reduce the displayed pytest count. The full backend count also includes many
other stories.

For a manual acceptance checklist, use five scenarios: structured reason entry,
active/inactive booking selection, coordinator notification/deduplication,
replacement display, and setup/turnaround boundaries. Migration compatibility
is a technical deployment check. Parameter variants are data rows, not new ACs.

## Deployment and verification

Apply SUPABASE_US12_2_FLAG_UNAVAILABLE_BOOKINGS.sql before deploying this branch's
API. Prerequisites are the existing venue bookings/unavailability schema,
coordinator assignment and coordinator-notification migrations. The canonical
script also repairs the earlier version's trigger and decision constraint.
It does not retroactively flag historical blackouts or rewrite notifications.

Do not run the removed three-script sequence from the original PR description.
Notifications have kind booking-conflict and NULL status; they do not change
the event status to Under Review. Needs-replacement bookings retain their
original decision metadata. Cancellation/replacement booking workflows are
outside this story; the UI directs the coordinator to Venue Staff.

CI runs the PostgreSQL integration suite against a disposable PostgreSQL 16
service in addition to the usual backend and frontend checks. The suite builds
the actual checked-in base schema and prerequisite migrations, creates a
unique temporary database, rolls back each scenario and drops that database.
It never reads SUPABASE_DB_URL or connects to the shared Supabase project.

To run locally, set TEST_POSTGRES_DSN to a disposable PostgreSQL server with
database/role creation privileges, then run from backend:

```sh
pytest integration/test_unavailability_db.py
```

Without that variable, integration tests skip locally; the CI step supplies it.
Live Supabase migration application and an authenticated browser smoke test
remain deployment checks, not claims made by these isolated tests.

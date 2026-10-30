# US11.2 change review

Apply `SUPABASE_US11_2_CHANGE_REVIEW.sql`, then
`SUPABASE_US11_2_REVIEW_FIXES.sql`, before deploying this backend/frontend pair.
If the first script has already been applied, run only the follow-up fixes script. It follows the existing event-needs, US11.1, notification, lifecycle,
US19.3 and exact-equipment-item migrations. It is additive and repeatable;
existing requests, review outcomes, notification kinds and RLS remain intact.
No live database migration was applied by this implementation.

## Behavior

- Ordinary proposals are available in Submitted, Approved, Planning, Pending
  Safety Check and Confirmed. Under Review permits amendments only after a
  clarification. All these operations preserve event status.
- Every question and proposal receives a revision and is retained in
  `events.review_state`. An amendment supersedes pending request rows;
  acceptance applies only the active proposal. Questions can repeat without
  a lifetime limit. Responses must change event fields; text alone is insufficient.
- Clients send `reviewRevision` when submitting, rejecting or asking a
  question, and `review_revision` when accepting. A stale revision returns 409.
  The optional parameters preserve existing API callers; the shipped UI sends
  the revision returned by the API. Direct Coordinator edits are blocked while
  a proposal is pending and use a transactional compare against `updated_at`.
- Accepted or direct changes to date/time/attendance commit a durable
  `arrangement_review_pending` marker. Rechecks preserve actual arrangement
  windows, quantities and statuses. Saved windows that do not cover the revised
  event, unsuitable/clashing venues, or insufficient reserved stock are flagged.
  A reservation is excluded from its own competing stock demand.
- Flags and reports are now committed together under the event version lock;
  stale rechecks cannot overwrite either flags or reports. Existing equipment
  reservations use peak concurrent demand, with half-open window boundaries.
- Safety readiness and its database transaction both block unresolved venue or
  equipment event-change conflicts and incomplete arrangement rechecks.
- Event-change conflict metadata is independent of setup/turnaround conflicts,
  safety re-review and venue replacement flags. Resolving one does not erase
  another. Existing reviewed arrangements are checked again after cancellation,
  rejection, equipment changes and conflict-list cleanup.
- Failed checks remain visibly incomplete. The assigned Coordinator can retry
  with `POST /events/{id}/arrangements/recheck`. Successful checks and individual
  failures appear in `arrangementReview`; failures do not cancel anything.
- New/revised proposals, questions, decisions and arrangement conflicts use the
  existing recipient-scoped read/unread notification list. Delivery failure is
  logged according to the existing best-effort notification convention.

Planned timestamps remain naive SGT. Recorded/audit timestamps remain UTC and
display in SGT. Reviewing metadata does not advance the event content version.

## Verification

The backend and frontend suites cover happy paths, invalid actors/states,
stale decisions, repeated amendments, validation limits, exact capacity/stock,
saved-window coverage, independent flags, partial failures, read/unread
notifications and timezone boundaries. The browser test uses isolated API
fixtures; backend API tests exercise the real routes and repositories.

Run the real migration/idempotency/rollback/concurrent-decision tests against a
disposable PostgreSQL server with `TEST_POSTGRES_DSN` set:

```powershell
python -m pytest integration/test_change_review_db.py
```

These tests create and remove a unique `us11_*` schema. They are wired into the
existing PostgreSQL CI job and skip locally when that variable is absent.

After deployment, verify a clarification round and accept an attendance change
on a Planning test event. Check that the status stays Planning, the Organiser
receives the decision, a venue below the new capacity is flagged, and the
Coordinator receives the arrangement notice. Investigate logged notification
errors and any events still showing incomplete arrangement checks.

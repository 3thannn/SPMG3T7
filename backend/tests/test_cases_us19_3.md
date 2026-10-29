# US19.3 — Check equipment availability and reserve it

Assumption: equipment overlap uses the equipment request’s needed-from/until
time, which is defaulted to the event’s start/end time. Editing event dates does
not change saved request dates. Times are SGT, without venue setup/turnaround.

Each request reserves its full quantity from one selected catalogue item. Time
windows are half-open: 09:00–10:00 and 10:00–11:00 do not overlap. Availability
subtracts every Reserved line overlapping the checked window, including lines
for the same event. Other statuses do not consume stock.

The Coordinator selects the exact catalogue entry (name, type, description and
location), not just its type. Selection itself does not reserve any stock. Tech
Support cannot substitute another catalogue item, even of the same type. The
Coordinator can change the selection when revising a Requested/Unavailable line.
Existing type-only requests remain readable but must have an item selected by
the Coordinator before they can be reserved. Known historical reservation links
are backfilled by the migration.

## Automated acceptance coverage

| Category | Scenario and expected result |
|---|---|
| Happy path | Requested → Reserved; item/event linkage persists, version increments, one unread Coordinator notice is written, line remains visible on event. |
| Exact item / negative | New requests require a valid catalogue ID; missing, zero, boolean and unknown IDs are refused. Names/types come from the selected catalogue row. Tech Support cannot change the selection or reserve another same-type item. |
| Legacy / recovery | Legacy type-only requests load without an item; availability is empty and reservation blocked until the Coordinator chooses one. Switching between same-type items changes the saved ID, displayed name and availability target. |
| Happy path | Requested → Unavailable with trimmed reason; reason persists and Coordinator receives it in an unread notice. |
| Recovery / workflow | While Planning, the assigned Coordinator can revise and resubmit Unavailable → Requested or remove the line. Resubmission clears the current Unavailable reason, increments version and notifies Tech Support even with unchanged fields. Prior decisions remain in history. |
| Recovery / safety | Unavailable blocks safety review until resolved. Resubmit → reserve, or remove the Unavailable line, then enter Pending Safety Check successfully when all other arrangements are ready. |
| Recovery / negative | Stale edit/removal, unauthorized roles and non-Planning events are refused. Tech Support cannot reopen an Unavailable line; resubmission does not bypass availability checks. Reserved lines remain protected. |
| Notification detail | Tech Support enters the Unavailable reason manually; that reason accompanies the Coordinator notice. Availability is checked again at reservation time. |
| Required example / boundary | 10 total − 2 out of service − 6 overlapping reserved = 2 available. Reserving 2 succeeds; 3 fails with shortfall 1 and remains Requested, without a Reserved notice. |
| Boundaries | Equal windows, containment and one-minute overlap consume stock; exact end/start adjacency in either direction does not. |
| Boundaries | Zero usable stock blocks reservation. Overnight request windows work even when outside the event window. |
| Negative | Blank Unavailable reason, wrong-type item, missing item/request, stale version, non-Planning event, boolean item ID and unauthorized roles are refused. |
| Quality / integrity | Multiple overlapping lines sum correctly; independent catalogue items do not share stock. Requested, Removed and Unavailable lines do not consume stock. |
| Quality / regression | Cancellation releases stock. Stock reduction/deletion cannot invalidate existing reservations; linked historic items cannot be deleted. Existing safety checks and Reserved-only safety review continue to apply. |
| UI / accessibility | Labelled selection and reason input; loading and error states; exact-stock Reserve enabled; shortage disables Reserve and announces shortfall; missing reason rejected. |
| UI / concurrency | Server conflict shown; request and availability refresh before retry; failed action never displays success. |
| SGT | Equipment windows stay in SGT under UTC, Singapore and New York viewer timezones, including midnight. Recorded request and notice timestamps use the existing UTC-to-SGT helper. |

Backend coverage: `test_equipment_reservations.py`, plus existing equipment,
cancellation, safety-check and safety-review suites. Frontend coverage:
`EquipmentReservation.test.tsx`, request detail, event equipment, notifications
and existing timestamp tests.

## PostgreSQL concurrency verification (opt-in)

`test_equipment_reservations_db.py` requires a **disposable**, fully migrated
database. It creates uniquely named fixtures, commits concurrent transactions,
and cleans up. Set `US19_DB_TEST_URL`, then run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_equipment_reservations_db.py -q
```

- Two independent connections request 6 units each from 8 usable units. Exactly
  one succeeds; the other gets insufficient stock. One Reserved notice is created.
- Repeated decision is refused; a second adjacent-window reservation succeeds.
- Concurrent Reserve and Unavailable decisions have exactly one winner and one notice.
- An injected notification failure rolls back the decision and its history entry.

These tests are skipped without the explicit test database URL. A passing
in-memory test suite does not verify PostgreSQL locking or migration execution.

## Manual review

1. Sign in as Tech Support, open a Requested line, choose an item, verify its
   total/out-of-service/reserved/available breakdown, and reserve it.
2. On the assigned Coordinator account, verify the unread notice opens the
   event and the Reserved line is visible there.
3. Repeat with insufficient stock, verify shortfall, then mark Unavailable with
   a reason; verify the Coordinator notice and reason on the event.
4. Check keyboard navigation, narrow-screen layout, loading feedback and retry.

## Rollout

Apply `SUPABASE_US19_3_EQUIPMENT_RESERVATIONS.sql` after the existing US19
requests, US4.6 cancellation, US20.1 registration and US17.2 safety migrations,
before deploying the backend/frontend changes. The migration extends existing
notification kinds and leaves teammates’ event/cancellation triggers in place.
It is rerunnable and does not reinterpret existing planned timestamps.

Then apply `SUPABASE_US19_EXACT_ITEM_REQUESTS.sql` before deploying the exact-item
UI/API. Run both scripts in order on a fresh database. The extra migration has
not been applied to the shared database by this implementation.

The historical backfill temporarily disables only the equipment-request Planning
guard and audit trigger, then restores both before continuing. It runs inside
the migration transaction and table lock. It copies known reservation item IDs
even for events beyond Planning and Removed lines on Cancelled events, without
changing status, quantity, dates, actor, version, or creating artificial audit
entries. Unselected legacy requests remain unselected; repeat runs preserve
existing selections. A failure rolls back the data and trigger-state changes.

`test_equipment_item_migration_db.py` executes the actual migration and production
trigger definitions in an isolated schema, rolled back after each test. With
`US19_DB_TEST_URL` set to a disposable PostgreSQL database whose user can create
schemas, run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_equipment_item_migration_db.py -q
```

It checks Planning/Pending Safety Check/Confirmed/Completed/Cancelled history,
repeat runs, preserved reservation data, restored Planning and audit guards,
foreign keys, and rollback after an injected failure. It is skipped without the
explicit test database URL; application unit tests cannot verify these DDL effects.

Verify the migration on a disposable database and run the concurrency tests
before shared deployment. It has not been applied to the shared database by
this implementation. Existing API readers need the migration because request
queries now include the decision columns. After deployment, smoke-test both
decisions and check backend logs for RPC/schema or notification failures.

"""The Supabase event store's queries, for the paths the route tests never reach.

The route tests run against `InMemoryEvents`. These drive `SupabaseEvents`
against the fake client in `tests.fakes` and check what it asks Postgres for:
the filters that decide who sees which events, the audit rows written beside a
status move, and the refusal when a guarded write matched nothing.
"""



EVENT_ID = 7

ROW = {
    "id": EVENT_ID,
    "name": "Faculty Welcome Night",
    "purpose": "Welcome the new intake.",
    "description": "Talks.",
    "proposed_date": "2026-11-02T18:00:00",
    "end_date": "2026-11-02T21:00:00",
    "expected_attendance": 120,
    "status": "Submitted",
    "organiser_id": 1,
    "coordinator_id": None,
    "created_at": "2026-10-01T09:00:00",
    "updated_at": "2026-10-01T09:00:00",
    "organiser": {"name": "Dylan"},
    "coordinator": None,
}

SUBMISSION = {
    "event_id": EVENT_ID,
    "id": 1,
    "old_status": "Draft",
    "new_status": "Submitted",
    "changed_at": "2026-10-01T09:05:00",
    "notes": None,
    "changed_by_id": 1,
    "users": {"name": "Dylan"},
}









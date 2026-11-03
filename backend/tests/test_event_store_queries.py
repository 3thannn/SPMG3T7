"""The Supabase event store's queries, for the paths the route tests never reach.

The route tests run against `InMemoryEvents`. These drive `SupabaseEvents`
against the fake client in `tests.fakes` and check what it asks Postgres for:
the filters that decide who sees which events, the audit rows written beside a
status move, and the refusal when a guarded write matched nothing.
"""

import pytest

from app.event_status import EventStatus
from app.event_store import (
    CHANGE_REQUESTS_TABLE,
    CHANGES_TABLE,
    EVENTS_TABLE,
    StaleEventStatus,
    SupabaseEvents,
    to_event,
)

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


class TestListing:
    def test_an_organiser_sees_only_their_own_events_and_no_drafts(self, fake):
        fake.rows = {EVENTS_TABLE: [dict(ROW)], CHANGES_TABLE: [dict(SUBMISSION)]}

        found = SupabaseEvents().list_events(organiser_id=1, include_drafts=False)

        events_query = fake.on(EVENTS_TABLE)[0]
        assert ("eq", "organiser_id", 1) in events_query.calls
        assert ("neq", "status", "Draft") in events_query.calls
        assert [event.id for event in found] == [EVENT_ID]


    def test_the_unassigned_queue_is_submitted_events_with_no_coordinator_oldest_first(
        self, fake
    ):
        fake.rows = {EVENTS_TABLE: [dict(ROW)]}

        found = SupabaseEvents().list_unassigned()

        calls = fake.on(EVENTS_TABLE)[0].calls
        assert ("eq", "status", "Submitted") in calls
        assert ("is", "coordinator_id", "null") in calls
        assert ("order", "submitted_at", False) in calls
        assert [event.id for event in found] == [EVENT_ID]



class TestCoordinatorEditsAreTracked:
    """US5.2, through US11.2's us11_edit: each changed field goes with its kind."""

    def edit(self, fake, answer, **changes):
        fake.rows = {EVENTS_TABLE: [dict(ROW)]}
        fake.rpc_answers = {"us11_edit": answer}
        previous = to_event(dict(ROW))
        fields = {
            "title": previous.title,
            "purpose": previous.purpose,
            "description": previous.description,
            "starts_at": previous.starts_at,
            "ends_at": previous.ends_at,
            "expected_attendance": previous.expected_attendance,
            **changes,
        }
        return SupabaseEvents().save_event_with_tracking(
            EVENT_ID, editor_id=2, previous_event=previous, **fields
        )


    def test_an_edit_the_database_refused_is_stale(self, fake):
        """It answers false when the event changed since the editor read it."""
        with pytest.raises(StaleEventStatus):
            self.edit(fake, False, title="Faculty Welcome Evening")


class TestStatusMoves:
    def test_submitting_writes_the_status_and_its_audit_row(self, fake):
        fake.rows = {EVENTS_TABLE: [dict(ROW)]}

        SupabaseEvents().submit_event(EVENT_ID, actor_id=1, from_status=EventStatus.DRAFT)

        [update] = fake.on(EVENTS_TABLE)[0].named("update")
        assert update[1]["status"] == "Submitted"
        [insert] = fake.on(CHANGES_TABLE)[0].named("insert")
        assert insert[1]["old_status"] == "Draft"
        assert insert[1]["new_status"] == "Submitted"
        assert insert[1]["changed_by_id"] == 1



    def test_a_clarification_on_an_event_that_is_gone_is_stale(self, fake):
        with pytest.raises(StaleEventStatus):
            SupabaseEvents().request_clarification(
                404,
                actor_id=2,
                from_status=EventStatus.SUBMITTED,
                message="Which room layout?",
            )

        assert fake.rpcs == []

    def test_planning_is_the_approved_to_planning_decision(self, fake):
        fake.rows = {EVENTS_TABLE: [dict(ROW)]}
        fake.rpc_answers = {"decide_event_status": True}

        SupabaseEvents().plan_event(EVENT_ID, actor_id=2)

        [(name, arguments)] = fake.rpcs
        assert name == "decide_event_status"
        assert arguments["p_expected_status"] == "Approved"
        assert arguments["p_new_status"] == "Planning"


    def test_completing_an_event_the_database_refused_is_stale(self, fake):
        fake.rpc_answers = {"complete_event_status": False}

        with pytest.raises(StaleEventStatus):
            SupabaseEvents().complete_event(EVENT_ID, actor_id=2)


def test_change_request_rows_are_read_for_the_whole_page_at_once(fake):
    fake.rows = {
        EVENTS_TABLE: [dict(ROW), dict(ROW, id=8)],
        CHANGE_REQUESTS_TABLE: [
            {
                "event_id": EVENT_ID,
                "changed_field": "name",
                "old_value": "Faculty Welcome Night",
                "new_value": "Faculty Welcome Evening",
                "change_type": "routine",
                "status": "pending",
            }
        ],
    }

    first, second = SupabaseEvents().list_events(organiser_id=None, include_drafts=True)

    assert len(fake.on(CHANGE_REQUESTS_TABLE)) == 1
    assert first.change_requested is True
    assert second.change_requested is False

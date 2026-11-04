from dataclasses import replace

import pytest

from app.event_store import EVENTS_TABLE, StaleEventStatus, SupabaseEvents
from tests.conftest import COORDINATOR_ID
from tests.test_change_requests import seed
from tests.test_change_review_us11_2 import booking, reservation
from tests.test_event_store_queries import ROW as EVENT_ROW


class TestStores:
    def test_a_review_refused_by_the_database_is_stale(self, fake):
        fake.rows = {EVENTS_TABLE: [dict(EVENT_ROW)]}
        fake.rpc_answers = {"us11_review": False}

        with pytest.raises(StaleEventStatus):
            SupabaseEvents()._workflow(7, 2, "clarify", {"message": "Why?"}, None)

    def test_committing_a_review_guards_on_the_version_it_reads(self, fake):
        fake.rows = {EVENTS_TABLE: [dict(EVENT_ROW)]}

        SupabaseEvents().set_arrangement_review(7, report=[], pending=False)

        [(name, arguments)] = fake.rpcs
        assert name == "us11_commit_arrangement_review"
        assert arguments["p_updated_at"] == EVENT_ROW["updated_at"]

    def test_an_edit_over_a_newer_version_is_stale(self, event_repository):
        event = seed(event_repository)
        older = replace(event, updated_at="2025-01-01T00:00:00")

        with pytest.raises(StaleEventStatus):
            event_repository.save_event_with_tracking(
                event.id,
                title="New",
                purpose=event.purpose,
                description=event.description,
                starts_at=event.starts_at,
                ends_at=event.ends_at,
                expected_attendance=event.expected_attendance,
                editor_id=COORDINATOR_ID,
                previous_event=older,
            )

    def test_a_review_whose_booking_moved_since_is_left_pending(
        self, event_repository, booking_repository
    ):
        event = seed(event_repository)
        booking_repository.bookings = [booking(event.id)]
        moved = {
            "id": 1,
            "status": "Confirmed",
            "startsAt": "2027-11-02T19:00",
            "endsAt": "2027-11-02T21:00",
            "headcount": 30,
        }

        result = event_repository.set_arrangement_review(
            event.id, report=[], pending=False, booking_flags=[moved]
        )

        assert result.arrangement_review_pending

    def test_a_review_whose_equipment_moved_since_is_left_pending(
        self, event_repository, equipment_repository
    ):
        event = seed(event_repository)
        equipment_repository.requests = [reservation(event.id)]
        moved = {"id": 1, "status": "Reserved", "version": 9}

        result = event_repository.set_arrangement_review(
            event.id, report=[], pending=False, equipment_flags=[moved]
        )

        assert result.arrangement_review_pending

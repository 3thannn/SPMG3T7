"""US11.2 and US9.5 paths test_change_review_us11_2.py does not reach.

Mostly failures and the quieter branches: an arrangement that cannot be loaded or
checked, a venue that left the catalogue, a slot taken since, an equipment line
that is not reserved, the stand-in stores refusing a read set that moved, and a
notice that cannot be written.
"""

from dataclasses import replace

import pytest

from app import arrangement_review, conflict_flags, notifications
from app.booking_store import BookingStatus
from app.equipment_store import Equipment, InMemoryEquipment, SupabaseEquipment
from app.event_status import EventStatus
from app.event_store import EVENTS_TABLE, StaleEventStatus, SupabaseEvents
from tests.conftest import COORDINATOR_ID
from tests.test_change_requests import seed
from tests.test_change_review_us11_2 import booking, question, reservation, submit
from tests.test_event_store_queries import ROW as EVENT_ROW

COORD = "Event Coordinator"
OWNER = "Event Organiser"


def failing(*_args, **_kwargs):
    raise RuntimeError("store unavailable")


class TestRecheck:
    def test_arrangements_that_cannot_be_loaded_leave_a_retry(
        self, event_repository, booking_repository, monkeypatch
    ):
        event = seed(event_repository)
        monkeypatch.setattr(booking_repository, "list_for_event", failing)

        result = arrangement_review.recheck(event)

        assert result.arrangement_review_pending

    def test_a_venue_gone_from_the_catalogue_is_flagged(
        self, event_repository, booking_repository
    ):
        event = seed(event_repository)
        booking_repository.bookings = [booking(event.id, venue_id=999, venue_name="Gone")]

        arrangement_review.recheck(event)

        assert "no longer available in the catalogue" in (
            booking_repository.get_booking(1).event_conflict_reason
        )

    def test_a_slot_taken_by_another_event_is_flagged(self, event_repository, booking_repository):
        event = seed(event_repository)
        booking_repository.bookings = [
            booking(event.id),
            booking(999, id=2, status=BookingStatus.CONFIRMED),
        ]

        arrangement_review.recheck(event)

        assert "clashes" in booking_repository.get_booking(1).event_conflict_reason

    def test_a_booking_that_cannot_be_checked_leaves_a_retry(
        self, event_repository, booking_repository, venue_repository, monkeypatch
    ):
        event = seed(event_repository)
        booking_repository.bookings = [booking(event.id)]
        monkeypatch.setattr(venue_repository, "get_venue", failing)

        result = arrangement_review.recheck(event)

        assert result.arrangement_review_pending
        assert any(entry["error"] for entry in result.arrangement_review)

    def test_a_line_not_yet_reserved_is_not_checked(self, event_repository, equipment_repository):
        event = seed(event_repository)
        equipment_repository.requests = [reservation(event.id, status="Requested")]

        result = arrangement_review.recheck(event)

        assert not result.arrangement_review_pending
        assert not result.arrangement_review


def test_listing_flags_rechecks_events_with_an_event_change_flag(
    event_repository, booking_repository, monkeypatch
):
    event = seed(event_repository)
    booking_repository.bookings = [booking(event.id, event_conflict_reason="Window too short.")]
    refreshed = []
    monkeypatch.setattr(arrangement_review, "refresh_if_reviewed", refreshed.append)

    conflict_flags.resolve_flagged()

    assert refreshed == [event.id]


class TestEquipmentStock:
    def test_the_database_answers_for_reserved_stock(self, fake):
        fake.rpc_answers = {"equipment_reservation_availability": [{"equipmentId": "1"}]}

        assert SupabaseEquipment().reservation_availability(30) == [{"equipmentId": "1"}]
        assert fake.rpcs == [("equipment_reservation_availability", {"p_request_id": 30})]

    def test_no_answer_is_no_stock(self, fake):
        assert SupabaseEquipment().reservation_availability(30) == []

    def test_a_line_that_is_not_reserved_has_no_reserved_stock(self):
        store = InMemoryEquipment()
        store.requests = [reservation(7, status="Requested")]

        assert store.reservation_availability(1) == []

    def test_a_reservation_that_does_not_overlap_takes_nothing(self):
        store = InMemoryEquipment()
        store.items = [Equipment(1, "Projector", "Projector", "", "Store", 2, 0, "")]
        store.requests = [
            reservation(7),
            reservation(8, id=2, starts_at="2027-11-03T18:00", ends_at="2027-11-03T21:00"),
        ]

        [stock] = store.reservation_availability(1)

        assert stock["shortfall"] == 0


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


class TestRoutes:
    def test_a_completed_event_cannot_be_edited(self, client, auth_headers, event_repository):
        event = seed(event_repository, status=EventStatus.COMPLETED)

        response = client.put(
            f"/events/{event.id}", json={"title": "Too late"}, headers=auth_headers(COORD)
        )

        assert response.status_code == 409

    def test_a_coordinator_edit_that_lost_a_race_is_a_conflict(
        self, client, auth_headers, event_repository, monkeypatch
    ):
        event = seed(event_repository, status=EventStatus.PLANNING)
        monkeypatch.setattr(event_repository, "save_event_with_tracking", failing_stale)

        response = client.put(
            f"/events/{event.id}",
            json={
                "title": "Seeded again",
                "purpose": event.purpose,
                "startsAt": event.starts_at,
                "endsAt": event.ends_at,
                "expectedAttendance": event.expected_attendance,
            },
            headers=auth_headers(COORD),
        )

        assert response.status_code == 409

    def test_answering_a_question_needs_a_revised_proposal(
        self, client, auth_headers, event_repository
    ):
        event = seed(event_repository, status=EventStatus.PLANNING)
        assert submit(client, auth_headers, event, 0, expectedAttendance=100).status_code == 200
        assert question(client, auth_headers, event, 1).status_code == 200

        repeated = submit(client, auth_headers, event, 2, expectedAttendance=100)

        assert repeated.status_code == 400
        assert repeated.json()["detail"]["message"] == (
            "Revise at least one proposed detail to answer the clarification."
        )


def failing_stale(*_args, **_kwargs):
    raise StaleEventStatus


class TestNotices:

    def test_a_later_clarification_survives_a_notice_that_cannot_be_written(
        self, event_repository, notification_repository, monkeypatch, caplog
    ):
        event = seed(event_repository, status=EventStatus.PLANNING)
        monkeypatch.setattr(notification_repository, "create_notice", failing)

        notifications.notify_clarification(event, "Which room layout?")

        assert "Could not notify clarification" in caplog.text

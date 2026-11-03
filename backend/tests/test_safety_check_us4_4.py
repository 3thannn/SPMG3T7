"""US4.4: the Pending Safety Check status and its transitions.

Acceptance criteria, and the tests that hold each one:

* 'Pending Safety Check' joins US4.1's label set -> `TestStatusLabel`.
* Planning -> Pending Safety Check once every active venue booking is Confirmed
  and equipment is reserved -> `TestReadinessRule`, `TestSendForSafetyCheck`.
* Pending Safety Check -> Confirmed when the Safety Officer approves ->
  `TestSafetyOfficerDecision`.
* Pending Safety Check -> Planning when the Safety Officer sends it back ->
  `TestSafetyOfficerDecision`.
* An event can't reach Confirmed any other way -> `TestOnlyWayToConfirmed`.
* Extends US4.3's allowlist rather than replacing it -> `TestOnlyWayToConfirmed`
  and the updated allowlist test in test_event_decisions.py.
"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from app import supabase_client
from app.booking_store import Booking, BookingStatus, ConflictFlag
from app.equipment_store import EquipmentRequest
from app.event_status import VALID_TRANSITIONS, EventStatus, transition_allowed
from app.event_store import Event, StaleEventStatus, StatusChange, SupabaseEvents
from app.permissions import Permission, Role, has_permission, permissions_for
from app.safety_check import (
    EQUIPMENT_RESERVED,
    KIND_SAFETY_RETURN,
    SAFETY_CHECK_REFUSAL_MESSAGES,
    SAFETY_NOTE_MAX,
    SafetyCheckRefusal,
    check_ready_for_safety_check,
    history_kind,
    safety_check_refusal_message,
)
from tests.conftest import (
    COORDINATOR_ID,
    ORGANISER_ID,
    SAFETY_OFFICER_ID,
    SUBMITTABLE_NEED_ATTRS,
    SUBMITTABLE_NEEDS,
)

PSC = EventStatus.PENDING_SAFETY_CHECK
#: Naive Singapore local time, as booking times are.
NOW = datetime(2099, 1, 1, 12, 0)
EVENT_ID = 700


def booking(
    booking_id=1,
    status=BookingStatus.CONFIRMED,
    *,
    event_id=EVENT_ID,
    venue_id=1,
    hold_expires_at="",
    conflict=None,
):
    return Booking(
        id=booking_id,
        event_id=event_id,
        venue_id=venue_id,
        venue_name="Great Hall",
        starts_at="2099-11-02T09:00",
        ends_at="2099-11-02T17:00",
        status=status,
        requested_by_id=COORDINATOR_ID,
        requested_at="2099-01-01T09:00",
        headcount=30,
        hold_expires_at=hold_expires_at,
        conflict=conflict,
    )


def equipment_line(line_id=1, status="Requested", *, event_id=EVENT_ID):
    return EquipmentRequest(
        id=line_id,
        event_id=event_id,
        equipment_type="Projector",
        quantity=1,
        technical_requirements="",
        support_notes="",
        starts_at="2099-11-02T09:00",
        ends_at="2099-11-02T17:00",
        status=status,
        requested_by_id=COORDINATOR_ID,
        created_at="2099-01-01T09:00",
        version=1,
    )


def seed_event(
    event_repository,
    status=EventStatus.PLANNING,
    *,
    event_id=EVENT_ID,
    coordinator_id=COORDINATOR_ID,
    history=(),
    updated_at="2099-01-01T09:00",
    change_requested=False,
):
    event = Event(
        id=event_id,
        title="Open House",
        purpose="Welcome visitors",
        description="Tours and talks.",
        starts_at="2099-11-02T09:00",
        ends_at="2099-11-02T17:00",
        expected_attendance=30,
        status=status,
        organiser_id=ORGANISER_ID,
        organiser_name="Dylan",
        created_at="2099-01-01T09:00",
        updated_at=updated_at,
        coordinator_id=coordinator_id,
        history=history,
        change_requested=change_requested,
        **SUBMITTABLE_NEED_ATTRS,
    )
    event_repository.events.append(event)
    return event


def ready_event(event_repository, booking_repository, **kwargs):
    """A Planning event with one Confirmed booking and nothing outstanding."""
    event = seed_event(event_repository, **kwargs)
    booking_repository.bookings.append(booking(event_id=event.id))
    return event


def ready(**overrides):
    arguments = {
        "status": EventStatus.PLANNING,
        "change_requested": False,
        "bookings": [booking()],
        "equipment": [],
        "now": NOW,
        **overrides,
    }
    return check_ready_for_safety_check(**arguments)


class TestStatusLabel:
    def test_pending_safety_check_is_a_status_between_planning_and_confirmed(self):
        labels = [str(item) for item in EventStatus]
        assert "Pending Safety Check" in labels
        assert labels.index("Planning") < labels.index("Pending Safety Check")
        assert labels.index("Pending Safety Check") < labels.index("Confirmed")

    def test_the_status_round_trips_through_the_api(self, client, auth_headers, event_repository):
        seed_event(event_repository, PSC)
        response = client.get(f"/events/{EVENT_ID}", headers=auth_headers("Event Coordinator"))
        assert response.status_code == 200
        assert response.json()["status"] == "Pending Safety Check"


class TestReadinessRule:
    """Planning -> Pending Safety Check 'once all active venue bookings are
    Confirmed and equipment is reserved'."""

    def test_a_confirmed_booking_and_no_equipment_is_ready(self):
        assert ready() is None

    @pytest.mark.parametrize(
        "status", [status for status in EventStatus if status is not EventStatus.PLANNING]
    )
    def test_only_a_planning_event_can_be_sent(self, status):
        assert ready(status=status) is SafetyCheckRefusal.NOT_PLANNING

    def test_a_pending_change_request_blocks_it(self):
        assert ready(change_requested=True) is SafetyCheckRefusal.CHANGE_PENDING

    def test_no_bookings_at_all_is_not_ready(self):
        assert ready(bookings=[]) is SafetyCheckRefusal.NO_CONFIRMED_VENUE

    def test_inactive_bookings_do_not_count_as_a_venue(self):
        inactive = [
            booking(1, BookingStatus.CANCELLED),
            booking(2, BookingStatus.REJECTED),
            booking(3, BookingStatus.HELD, hold_expires_at="2098-12-31T09:00"),
        ]
        assert ready(bookings=inactive) is SafetyCheckRefusal.NO_CONFIRMED_VENUE

    def test_a_requested_booking_alongside_a_confirmed_one_blocks_it(self):
        bookings = [booking(1), booking(2, BookingStatus.REQUESTED, venue_id=3)]
        assert ready(bookings=bookings) is SafetyCheckRefusal.VENUE_NOT_CONFIRMED

    def test_a_live_hold_blocks_it(self):
        bookings = [booking(1), booking(2, BookingStatus.HELD, hold_expires_at="2099-01-02T09:00")]
        assert ready(bookings=bookings) is SafetyCheckRefusal.VENUE_NOT_CONFIRMED

    def test_cancelled_rejected_and_expired_bookings_are_ignored(self):
        bookings = [
            booking(1),
            booking(2, BookingStatus.CANCELLED),
            booking(3, BookingStatus.REJECTED),
            # Expiry itself counts as expired (US14.3).
            booking(4, BookingStatus.HELD, hold_expires_at="2099-01-01T12:00"),
        ]
        assert ready(bookings=bookings) is None

    def test_a_confirmed_booking_flagged_for_conflict_blocks_it(self):
        flagged = booking(conflict=ConflictFlag(flagged_at="2099-01-01T09:00", reason="Clash"))
        assert ready(bookings=[flagged]) is SafetyCheckRefusal.VENUE_CONFLICT

    def test_an_equipment_line_still_requested_blocks_it(self):
        lines = [equipment_line(1, EQUIPMENT_RESERVED), equipment_line(2, "Requested")]
        assert ready(equipment=lines) is SafetyCheckRefusal.EQUIPMENT_NOT_RESERVED

    def test_every_equipment_line_reserved_is_ready(self):
        lines = [equipment_line(1, EQUIPMENT_RESERVED), equipment_line(2, EQUIPMENT_RESERVED)]
        assert ready(equipment=lines) is None

    def test_venues_are_checked_before_equipment(self):
        result = ready(
            bookings=[booking(1, BookingStatus.REQUESTED)], equipment=[equipment_line()]
        )
        assert result is SafetyCheckRefusal.VENUE_NOT_CONFIRMED

    def test_without_a_clock_it_uses_singapore_now(self):
        far_future_hold = booking(2, BookingStatus.HELD, hold_expires_at="9999-01-01T00:00")
        assert (
            check_ready_for_safety_check(
                status=EventStatus.PLANNING,
                change_requested=False,
                bookings=[booking(1), far_future_hold],
                equipment=[],
            )
            is SafetyCheckRefusal.VENUE_NOT_CONFIRMED
        )

    @pytest.mark.parametrize("reason", list(SafetyCheckRefusal))
    def test_every_refusal_explains_itself(self, reason):
        assert safety_check_refusal_message(reason) == SAFETY_CHECK_REFUSAL_MESSAGES[reason]
        assert safety_check_refusal_message(reason).endswith(".")


class TestSendForSafetyCheck:
    def test_readiness_says_ready(self, client, auth_headers, event_repository, booking_repository):
        ready_event(event_repository, booking_repository)
        response = client.get(
            f"/events/{EVENT_ID}/safety-check", headers=auth_headers("Event Coordinator")
        )
        assert response.status_code == 200
        assert response.json() == {"ready": True, "reason": "", "message": ""}

    def test_readiness_says_what_is_outstanding(
        self, client, auth_headers, event_repository, booking_repository, equipment_repository
    ):
        ready_event(event_repository, booking_repository)
        equipment_repository.requests.append(equipment_line())
        response = client.get(
            f"/events/{EVENT_ID}/safety-check", headers=auth_headers("Event Coordinator")
        )
        assert response.status_code == 200
        assert response.json() == {
            "ready": False,
            "reason": "equipment-not-reserved",
            "message": safety_check_refusal_message(SafetyCheckRefusal.EQUIPMENT_NOT_RESERVED),
        }

    def test_the_assigned_coordinator_sends_a_ready_event(
        self, client, auth_headers, event_repository, booking_repository
    ):
        ready_event(event_repository, booking_repository)
        response = client.post(
            f"/events/{EVENT_ID}/safety-check", headers=auth_headers("Event Coordinator")
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "Pending Safety Check"
        last = body["history"][-1]
        assert (last["from"], last["to"], last["byId"], last["byName"]) == (
            "Planning", "Pending Safety Check", str(COORDINATOR_ID), "Priya",
        )
        assert last["at"]
        assert last["kind"] == ""
        assert event_repository.get_event(EVENT_ID).status is PSC

    def test_a_refused_send_names_the_reason_and_changes_nothing(
        self, client, auth_headers, event_repository, booking_repository
    ):
        event = seed_event(event_repository)
        booking_repository.bookings.append(booking(status=BookingStatus.REQUESTED))
        response = client.post(
            f"/events/{EVENT_ID}/safety-check", headers=auth_headers("Event Coordinator")
        )
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["reason"] == "venue-not-confirmed"
        assert detail["message"] == safety_check_refusal_message(
            SafetyCheckRefusal.VENUE_NOT_CONFIRMED
        )
        assert event_repository.get_event(EVENT_ID) == event

    def test_a_pending_change_request_blocks_the_send(
        self, client, auth_headers, event_repository, booking_repository
    ):
        ready_event(event_repository, booking_repository, change_requested=True)
        response = client.post(
            f"/events/{EVENT_ID}/safety-check", headers=auth_headers("Event Coordinator")
        )
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "change-pending"

    @pytest.mark.parametrize(
        "status",
        [EventStatus.SUBMITTED, EventStatus.UNDER_REVIEW, EventStatus.APPROVED,
         EventStatus.CONFIRMED, EventStatus.COMPLETED],
    )
    def test_only_planning_moves_to_pending_safety_check(
        self, client, auth_headers, event_repository, booking_repository, status
    ):
        event = ready_event(event_repository, booking_repository, status=status)
        response = client.post(
            f"/events/{EVENT_ID}/safety-check", headers=auth_headers("Event Coordinator")
        )
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "invalid-transition"
        assert event_repository.get_event(EVENT_ID) == event

    def test_sending_twice_is_refused(
        self, client, auth_headers, event_repository, booking_repository
    ):
        ready_event(event_repository, booking_repository, status=PSC)
        response = client.post(
            f"/events/{EVENT_ID}/safety-check", headers=auth_headers("Event Coordinator")
        )
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "not-planning"

    def test_another_coordinators_event_is_not_found(
        self, client, auth_headers, event_repository, booking_repository
    ):
        ready_event(event_repository, booking_repository, coordinator_id=999)
        coordinator = auth_headers("Event Coordinator")
        path = f"/events/{EVENT_ID}/safety-check"
        assert client.get(path, headers=coordinator).status_code == 404
        assert client.post(path, headers=coordinator).status_code == 404

    @pytest.mark.parametrize(
        "role", ["Event Organiser", "Event Coordinator Lead", "Venue Staff", "Safety Officer",
                 "Technical Support"],
    )
    def test_only_a_coordinator_may_send(
        self, client, auth_headers, event_repository, booking_repository, role
    ):
        ready_event(event_repository, booking_repository)
        headers = auth_headers(role)
        assert client.get(f"/events/{EVENT_ID}/safety-check", headers=headers).status_code == 403
        response = client.post(f"/events/{EVENT_ID}/safety-check", headers=headers)
        assert response.status_code == 403
        assert "send events for a safety check" in response.json()["detail"]["message"]
        assert event_repository.get_event(EVENT_ID).status is EventStatus.PLANNING

    def test_a_race_lost_in_the_store_is_reported_as_stale(
        self, client, auth_headers, event_repository, booking_repository, monkeypatch
    ):
        ready_event(event_repository, booking_repository)

        def lost(*_args, **_kwargs):
            raise StaleEventStatus

        monkeypatch.setattr(event_repository, "send_to_safety_check", lost)
        response = client.post(
            f"/events/{EVENT_ID}/safety-check", headers=auth_headers("Event Coordinator")
        )
        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "invalid-transition"

    def test_unknown_event(self, client, auth_headers):
        coordinator = auth_headers("Event Coordinator")
        assert client.post("/events/abc/safety-check", headers=coordinator).status_code == 404
        assert client.get("/events/12345/safety-check", headers=coordinator).status_code == 404


class TestSafetyOfficerQueue:
    def test_only_pending_events_longest_waiting_first(
        self, client, auth_headers, event_repository
    ):
        def entered(at):
            return (StatusChange(EventStatus.PLANNING, PSC, at, COORDINATOR_ID, "Priya"),)

        seed_event(event_repository, PSC, event_id=1, history=entered("2099-01-03T09:00"))
        seed_event(event_repository, PSC, event_id=2, history=entered("2099-01-02T09:00"))
        # No entry for the move: falls back to when the event last changed.
        seed_event(event_repository, PSC, event_id=3, updated_at="2099-01-02T10:00")
        seed_event(event_repository, EventStatus.PLANNING, event_id=4)
        seed_event(event_repository, EventStatus.CONFIRMED, event_id=5)
        response = client.get("/events/safety-check", headers=auth_headers("Safety Officer"))
        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == ["2", "3", "1"]
        assert {item["status"] for item in response.json()} == {"Pending Safety Check"}


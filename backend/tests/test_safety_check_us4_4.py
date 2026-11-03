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

    def test_a_resent_event_joins_the_back_of_the_queue(
        self, client, auth_headers, event_repository
    ):
        history = (
            StatusChange(EventStatus.PLANNING, PSC, "2099-01-01T09:00", COORDINATOR_ID, "Priya"),
            StatusChange(PSC, EventStatus.PLANNING, "2099-01-01T10:00", SAFETY_OFFICER_ID, "Alex"),
            StatusChange(EventStatus.PLANNING, PSC, "2099-01-05T09:00", COORDINATOR_ID, "Priya"),
        )
        seed_event(event_repository, PSC, event_id=1, history=history)
        seed_event(
            event_repository, PSC, event_id=2,
            history=(StatusChange(EventStatus.PLANNING, PSC, "2099-01-03T09:00", 2, "Priya"),),
        )
        response = client.get("/events/safety-check", headers=auth_headers("Safety Officer"))
        assert [item["id"] for item in response.json()] == ["2", "1"]

    @pytest.mark.parametrize(
        "role", ["Event Organiser", "Event Coordinator", "Event Coordinator Lead"]
    )
    def test_the_queue_is_the_safety_officers(self, client, auth_headers, role):
        assert client.get("/events/safety-check", headers=auth_headers(role)).status_code == 403

    def test_the_safety_officer_opens_a_pending_event(self, client, auth_headers, event_repository):
        seed_event(event_repository, PSC)
        response = client.get(f"/events/{EVENT_ID}", headers=auth_headers("Safety Officer"))
        assert response.status_code == 200
        assert response.json()["status"] == "Pending Safety Check"

    @pytest.mark.parametrize(
        "status", [EventStatus.PLANNING, EventStatus.CONFIRMED, EventStatus.DRAFT]
    )
    def test_the_safety_officer_sees_nothing_else(
        self, client, auth_headers, event_repository, status
    ):
        seed_event(event_repository, status)
        response = client.get(f"/events/{EVENT_ID}", headers=auth_headers("Safety Officer"))
        assert response.status_code == 404

    def test_the_safety_officer_has_no_events_list(self, client, auth_headers):
        assert client.get("/events", headers=auth_headers("Safety Officer")).status_code == 403


class TestSafetyOfficerDecision:
    def test_approval_leaves_it_for_the_coordinator_to_confirm(
        self, client, auth_headers, event_repository
    ):
        """US4.7: approving no longer confirms the event; the Coordinator does."""
        seed_event(event_repository, PSC)
        response = client.post(
            f"/events/{EVENT_ID}/safety-check/approve", headers=auth_headers("Safety Officer")
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "Pending Safety Check"
        assert body["safetyApproved"] is True
        assert body["history"] == []  # no status move, so nothing new in the trail
        assert event_repository.get_event(EVENT_ID).status is EventStatus.PENDING_SAFETY_CHECK

    def test_sending_back_returns_it_to_planning_with_the_note(
        self, client, auth_headers, event_repository, notification_repository
    ):
        seed_event(event_repository, PSC)
        response = client.post(
            f"/events/{EVENT_ID}/safety-check/return",
            json={"note": "  Add a second fire marshal.  "},
            headers=auth_headers("Safety Officer"),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "Planning"
        last = body["history"][-1]
        assert (last["from"], last["to"], last["byId"], last["notes"], last["kind"]) == (
            "Pending Safety Check", "Planning", str(SAFETY_OFFICER_ID),
            "Add a second fire marshal.", KIND_SAFETY_RETURN,
        )
        notices = notification_repository.list_for_user(COORDINATOR_ID)
        assert len(notices) == 1
        assert "Add a second fire marshal." in notices[0].message

    def test_a_returned_event_can_be_sent_again_and_needs_a_fresh_decision(
        self, client, auth_headers, event_repository, booking_repository
    ):
        ready_event(event_repository, booking_repository, status=PSC)
        officer = auth_headers("Safety Officer")
        coordinator = auth_headers("Event Coordinator")
        returned = client.post(
            f"/events/{EVENT_ID}/safety-check/return", json={"note": "Fix exits"}, headers=officer
        )
        assert returned.json()["status"] == "Planning"
        resent = client.post(f"/events/{EVENT_ID}/safety-check", headers=coordinator)
        assert resent.json()["status"] == "Pending Safety Check"
        approved = client.post(f"/events/{EVENT_ID}/safety-check/approve", headers=officer)
        assert approved.json()["safetyApproved"] is True
        confirmed = client.post(f"/events/{EVENT_ID}/confirm", headers=coordinator)
        assert confirmed.json()["status"] == "Confirmed"
        moves = [(h["from"], h["to"]) for h in confirmed.json()["history"]][-3:]
        assert moves == [
            ("Pending Safety Check", "Planning"),
            ("Planning", "Pending Safety Check"),
            ("Pending Safety Check", "Confirmed"),
        ]

    @pytest.mark.parametrize("note", ["", "   "])
    def test_sending_back_needs_a_note(self, client, auth_headers, event_repository, note):
        event = seed_event(event_repository, PSC)
        response = client.post(
            f"/events/{EVENT_ID}/safety-check/return", json={"note": note},
            headers=auth_headers("Safety Officer"),
        )
        assert response.status_code == 400
        assert event_repository.get_event(EVENT_ID) == event

    def test_the_note_has_a_limit(self, client, auth_headers, event_repository):
        seed_event(event_repository, PSC)
        officer = auth_headers("Safety Officer")
        too_long = client.post(
            f"/events/{EVENT_ID}/safety-check/return",
            json={"note": "x" * (SAFETY_NOTE_MAX + 1)}, headers=officer,
        )
        assert too_long.status_code == 400
        at_limit = client.post(
            f"/events/{EVENT_ID}/safety-check/return",
            json={"note": "x" * SAFETY_NOTE_MAX}, headers=officer,
        )
        assert at_limit.status_code == 200

    @pytest.mark.parametrize("action", ["approve", "return"])
    def test_an_event_not_pending_cannot_be_decided(
        self, client, auth_headers, event_repository, action
    ):
        event = seed_event(event_repository, EventStatus.PLANNING)
        response = client.post(
            f"/events/{EVENT_ID}/safety-check/{action}", json={"note": "n"},
            headers=auth_headers("Safety Officer"),
        )
        assert response.status_code == 404
        assert event_repository.get_event(EVENT_ID) == event

    @pytest.mark.parametrize(
        "role", ["Event Organiser", "Event Coordinator", "Event Coordinator Lead", "Venue Staff",
                 "Technical Support"],
    )
    @pytest.mark.parametrize("action", ["approve", "return"])
    def test_only_the_safety_officer_decides(
        self, client, auth_headers, event_repository, role, action
    ):
        seed_event(event_repository, PSC)
        response = client.post(
            f"/events/{EVENT_ID}/safety-check/{action}", json={"note": "n"},
            headers=auth_headers(role),
        )
        assert response.status_code == 403
        assert "review event safety" in response.json()["detail"]["message"]
        assert event_repository.get_event(EVENT_ID).status is PSC

    def test_a_check_decided_twice_is_refused(self, client, auth_headers, event_repository):
        """US4.7: an approval leaves the event Pending Safety Check, and the same
        stay still cannot be decided again."""
        seed_event(event_repository, PSC)
        officer = auth_headers("Safety Officer")
        assert client.post(
            f"/events/{EVENT_ID}/safety-check/approve", headers=officer
        ).status_code == 200
        response = client.post(f"/events/{EVENT_ID}/safety-check/approve", headers=officer)
        assert response.status_code == 409
        assert response.json()["detail"]["message"] == (
            "This safety check was already decided. Refresh it and try again."
        )


class TestOnlyWayToConfirmed:
    @pytest.mark.parametrize("before", list(EventStatus))
    def test_confirmed_is_only_reachable_from_pending_safety_check(self, before):
        expected = before in (PSC, EventStatus.CONFIRMED)
        assert transition_allowed(from_status=before, to_status=EventStatus.CONFIRMED) is expected

    @pytest.mark.parametrize("before", list(EventStatus))
    def test_pending_safety_check_is_only_reachable_from_planning(self, before):
        expected = before in (EventStatus.PLANNING, PSC)
        assert transition_allowed(from_status=before, to_status=PSC) is expected

    def test_pending_safety_check_leaves_only_for_confirmed_or_planning(self):
        # US4.6 adds the one way out every open event has: being cancelled.
        assert {after for before, after in VALID_TRANSITIONS if before is PSC} == {
            EventStatus.CONFIRMED, EventStatus.PLANNING, EventStatus.CANCELLED,
        }

    def test_us4_3_transitions_are_kept(self):
        assert {
            (EventStatus.DRAFT, EventStatus.SUBMITTED),
            (EventStatus.SUBMITTED, EventStatus.UNDER_REVIEW),
            (EventStatus.UNDER_REVIEW, EventStatus.APPROVED),
            (EventStatus.UNDER_REVIEW, EventStatus.REJECTED),
        } <= VALID_TRANSITIONS

    def test_planning_no_longer_skips_to_confirmed(
        self, client, auth_headers, event_repository
    ):
        """The old way a Confirmed event could only be set up (by hand) is not a route."""
        seed_event(event_repository, EventStatus.PLANNING)
        response = client.post(
            f"/events/{EVENT_ID}/safety-check/approve", headers=auth_headers("Safety Officer")
        )
        assert response.status_code == 404
        assert event_repository.get_event(EVENT_ID).status is EventStatus.PLANNING

    def test_end_to_end_from_draft_to_confirmed(
        self, client, auth_headers, event_repository, booking_repository
    ):
        organiser = auth_headers("Event Organiser")
        coordinator = auth_headers("Event Coordinator")
        event = {
            "title": "Open House",
            "purpose": "Welcome visitors",
            "description": "Tours and talks.",
            "startsAt": "2099-11-02T09:00",
            "endsAt": "2099-11-02T17:00",
            "expectedAttendance": 30,
            **SUBMITTABLE_NEEDS,
        }
        event_id = client.post("/events", json=event, headers=organiser).json()["id"]
        assert client.post(f"/events/{event_id}/submit", headers=organiser).status_code == 200
        assert client.post(
            f"/events/{event_id}/assign", json={"coordinatorId": str(COORDINATOR_ID)},
            headers=auth_headers("Event Coordinator Lead"),
        ).status_code == 200
        assert client.post(f"/events/{event_id}/approve", headers=coordinator).status_code == 200
        requested = client.post(
            f"/events/{event_id}/bookings",
            json={"venueId": "1", "startsAt": event["startsAt"], "endsAt": event["endsAt"]},
            headers=coordinator,
        )
        assert requested.status_code == 201, requested.text

        waiting = client.get(f"/events/{event_id}/safety-check", headers=coordinator).json()
        assert waiting["reason"] == "venue-not-confirmed"
        decided = client.post(
            f"/booking-requests/{requested.json()['id']}/approve",
            headers=auth_headers("Venue Staff"),
        )
        assert decided.status_code == 200, decided.text
        assert client.get(f"/events/{event_id}/safety-check", headers=coordinator).json()["ready"]

        sent = client.post(f"/events/{event_id}/safety-check", headers=coordinator)
        assert sent.json()["status"] == "Pending Safety Check"
        approved = client.post(
            f"/events/{event_id}/safety-check/approve", headers=auth_headers("Safety Officer")
        )
        assert approved.json()["status"] == "Pending Safety Check"
        # US4.7: the Coordinator confirms once the Safety Officer has approved.
        confirmed = client.post(f"/events/{event_id}/confirm", headers=coordinator)
        assert confirmed.json()["status"] == "Confirmed"
        assert [(h["from"], h["to"]) for h in confirmed.json()["history"]] == [
            (None, "Draft"),
            ("Draft", "Submitted"),
            ("Submitted", "Under Review"),
            ("Under Review", "Approved"),
            ("Approved", "Planning"),
            ("Planning", "Pending Safety Check"),
            ("Pending Safety Check", "Confirmed"),
        ]


class TestHistoryKind:
    def test_only_a_return_from_the_safety_check_is_labelled(self):
        assert history_kind(from_status=PSC, to_status=EventStatus.PLANNING) == KIND_SAFETY_RETURN
        assert history_kind(from_status=PSC, to_status=EventStatus.CONFIRMED) == ""
        assert history_kind(from_status=EventStatus.APPROVED, to_status=EventStatus.PLANNING) == ""
        assert history_kind(from_status=None, to_status=EventStatus.DRAFT) == ""


class TestPermissions:
    def test_coordinators_send_and_safety_officers_decide(self):
        assert has_permission(Role.COORDINATOR, Permission.SAFETY_SUBMIT)
        assert has_permission(Role.SAFETY_OFFICER, Permission.SAFETY_REVIEW)
        assert [role for role in Role if has_permission(role, Permission.SAFETY_SUBMIT)] == [
            Role.COORDINATOR
        ]
        assert [role for role in Role if has_permission(role, Permission.SAFETY_REVIEW)] == [
            Role.SAFETY_OFFICER
        ]

    def test_the_safety_officer_reads_no_events_lists(self):
        granted = permissions_for(Role.SAFETY_OFFICER)
        assert Permission.EVENTS_READ_ALL not in granted
        assert Permission.EVENTS_READ_SUBMITTED not in granted


class TestInMemoryStore:
    def test_send_refuses_an_event_that_moved_or_is_not_theirs(self, event_repository):
        seed_event(event_repository, EventStatus.APPROVED, event_id=1)
        seed_event(event_repository, EventStatus.PLANNING, event_id=2, coordinator_id=999)
        with pytest.raises(StaleEventStatus):
            event_repository.send_to_safety_check(1, actor_id=COORDINATOR_ID)
        with pytest.raises(StaleEventStatus):
            event_repository.send_to_safety_check(2, actor_id=COORDINATOR_ID)

    def test_decide_refuses_an_event_no_longer_pending(self, event_repository):
        seed_event(event_repository, EventStatus.CONFIRMED)
        with pytest.raises(StaleEventStatus):
            event_repository.decide_safety_check(
                EVENT_ID, actor_id=SAFETY_OFFICER_ID, to_status=EventStatus.CONFIRMED, note=""
            )


class RpcAdmin:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def rpc(self, name, arguments):
        self.calls.append((name, arguments))
        return self

    def execute(self):
        return SimpleNamespace(data=self.result)


class TestSupabaseStore:
    def test_send_uses_the_atomic_rpc(self, monkeypatch):
        admin = RpcAdmin(True)
        marker = object()
        store = SupabaseEvents()
        monkeypatch.setattr(supabase_client, "admin", lambda: admin)
        monkeypatch.setattr(store, "get_event", lambda _id: marker)
        assert store.send_to_safety_check(42, actor_id=COORDINATOR_ID) is marker
        assert admin.calls == [
            ("send_event_to_safety_check", {"p_event_id": 42, "p_coordinator_id": COORDINATOR_ID})
        ]
        admin.result = False
        with pytest.raises(StaleEventStatus):
            store.send_to_safety_check(42, actor_id=COORDINATOR_ID)

    def test_decide_uses_the_atomic_rpc(self, monkeypatch):
        admin = RpcAdmin(True)
        marker = object()
        store = SupabaseEvents()
        monkeypatch.setattr(supabase_client, "admin", lambda: admin)
        monkeypatch.setattr(store, "get_event", lambda _id: marker)
        assert store.decide_safety_check(
            42, actor_id=SAFETY_OFFICER_ID, to_status=EventStatus.CONFIRMED, note=""
        ) is marker
        assert store.decide_safety_check(
            42, actor_id=SAFETY_OFFICER_ID, to_status=EventStatus.PLANNING, note="Fix exits"
        ) is marker
        assert admin.calls == [
            ("decide_safety_check", {
                "p_event_id": 42, "p_new_status": "Confirmed",
                "p_officer_id": SAFETY_OFFICER_ID, "p_notes": None,
            }),
            ("decide_safety_check", {
                "p_event_id": 42, "p_new_status": "Planning",
                "p_officer_id": SAFETY_OFFICER_ID, "p_notes": "Fix exits",
            }),
        ]
        admin.result = None
        with pytest.raises(StaleEventStatus):
            store.decide_safety_check(
                42, actor_id=SAFETY_OFFICER_ID, to_status=EventStatus.CONFIRMED, note=""
            )

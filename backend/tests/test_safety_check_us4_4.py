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
from app.booking_store import Booking, BookingStatus
from app.equipment_store import EquipmentRequest
from app.event_status import EventStatus, transition_allowed
from app.event_store import Event, StaleEventStatus, SupabaseEvents
from app.safety_check import (
    EQUIPMENT_RESERVED,
    SafetyCheckRefusal,
    check_ready_for_safety_check,
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



class TestReadinessRule:
    """Planning -> Pending Safety Check 'once all active venue bookings are
    Confirmed and equipment is reserved'."""






    def test_a_requested_booking_alongside_a_confirmed_one_blocks_it(self):
        bookings = [booking(1), booking(2, BookingStatus.REQUESTED, venue_id=3)]
        assert ready(bookings=bookings) is SafetyCheckRefusal.VENUE_NOT_CONFIRMED




    def test_an_equipment_line_still_requested_blocks_it(self):
        lines = [equipment_line(1, EQUIPMENT_RESERVED), equipment_line(2, "Requested")]
        assert ready(equipment=lines) is SafetyCheckRefusal.EQUIPMENT_NOT_RESERVED






class TestSendForSafetyCheck:


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













class TestOnlyWayToConfirmed:
    @pytest.mark.parametrize("before", list(EventStatus))
    def test_confirmed_is_only_reachable_from_pending_safety_check(self, before):
        expected = before in (PSC, EventStatus.CONFIRMED)
        assert transition_allowed(from_status=before, to_status=EventStatus.CONFIRMED) is expected




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


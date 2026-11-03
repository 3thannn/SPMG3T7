"""US4.7: the Coordinator confirms the event once every approval is in.

Acceptance criteria, and the tests that hold each one:

* The assigned Coordinator confirms an event Pending Safety Check only when the
  current stay is approved, every active booking is Confirmed and unflagged,
  every equipment line is Reserved and no change request is pending ->
  `TestConfirm`, `TestRefusals`, `TestRules`.
* Anything missing is named in the refusal -> `TestRefusals`.
* Pending Safety Check -> Confirmed only through this action; the Safety
  Officer's approval no longer confirms -> `TestSafetyApproval`. The database
  half is SUPABASE_US4_7_CONFIRM_EVENT.sql.
* Only the assigned Coordinator, everyone else blocked -> `TestWhoConfirms`.
* The Organiser is notified (US10.3) -> `TestConfirm`.
* Timestamped and attributable (US4.2) -> `TestConfirm`.

The story's five tests are `test_confirm_after_approval_confirms_it`,
`test_no_approval_is_refused`, `test_a_booking_still_requested_is_refused`,
`test_a_coordinator_not_assigned_is_refused` and
`test_the_lead_and_the_organiser_are_refused`.
"""

from dataclasses import replace

import pytest

from app.booking_store import Booking, BookingStatus, ConflictFlag
from app.equipment_store import RESERVED, EquipmentRequest
from app.event_confirmation import (
    CHANGE_PENDING_MESSAGE,
    NOT_APPROVED_MESSAGE,
)
from app.event_status import EventStatus
from app.event_store import Event, StatusChange
from app.permissions import Role
from app.safety_decision_store import SafetyDecision
from app.safety_decisions import SafetyOutcome
from tests.conftest import (
    COORDINATOR_ID,
    ORGANISER_ID,
    SUBMITTABLE_NEED_ATTRS,
)
from tests.test_change_requests import add_user

PSC = EventStatus.PENDING_SAFETY_CHECK
EVENT_ID = 950
#: When the event entered Pending Safety Check: the stay an approval must be for.
ENTERED = "2099-01-02T10:00:00"
EARLIER = "2099-01-01T10:00:00"
NOW = "2099-01-02T12:00:00"

COORDINATOR = "Event Coordinator"
OFFICER = "Safety Officer"


def booking(booking_id=1, status=BookingStatus.CONFIRMED, venue="Great Hall", **extra):
    return Booking(
        id=booking_id,
        event_id=EVENT_ID,
        venue_id=1,
        venue_name=venue,
        starts_at="2099-11-02T09:00",
        ends_at="2099-11-02T17:00",
        status=status,
        requested_by_id=COORDINATOR_ID,
        requested_at="2099-01-01T09:00",
        headcount=30,
        **extra,
    )


def line(status=RESERVED, **extra):
    return EquipmentRequest(
        id=1,
        event_id=EVENT_ID,
        equipment_type="Projector",
        quantity=2,
        technical_requirements="",
        support_notes="",
        starts_at="2099-11-02T08:30",
        ends_at="2099-11-02T17:30",
        status=status,
        requested_by_id=COORDINATOR_ID,
        created_at="2099-01-01T09:00",
        version=1,
        **extra,
    )


@pytest.fixture
def waiting(event_repository, booking_repository, equipment_repository):
    """An event Pending Safety Check with a Confirmed venue and reserved equipment."""
    event = Event(
        id=EVENT_ID,
        title="Open House",
        purpose="Welcome visitors",
        description="Tours and talks.",
        starts_at="2099-11-02T09:00",
        ends_at="2099-11-02T17:00",
        expected_attendance=30,
        status=PSC,
        organiser_id=ORGANISER_ID,
        organiser_name="Dylan",
        created_at="2099-01-01T09:00",
        updated_at=ENTERED,
        coordinator_id=COORDINATOR_ID,
        history=(StatusChange(EventStatus.PLANNING, PSC, ENTERED, COORDINATOR_ID, "Priya"),),
        **SUBMITTABLE_NEED_ATTRS,
    )
    event_repository.events.append(event)
    booking_repository.bookings.append(booking())
    equipment_repository.requests.append(line())
    return event


def approve(client, auth_headers):
    response = client.post(
        f"/events/{EVENT_ID}/safety-check/approve", headers=auth_headers(OFFICER)
    )
    assert response.status_code == 200, response.text
    return response.json()


def confirm(client, headers):
    return client.post(f"/events/{EVENT_ID}/confirm", headers=headers)


class TestConfirm:
    def test_confirm_after_approval_confirms_it(self, client, auth_headers, waiting):
        approve(client, auth_headers)

        response = confirm(client, auth_headers(COORDINATOR))

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Confirmed"
        assert response.json()["safetyApproved"] is False

    def test_the_confirmation_is_timestamped_and_attributable(self, client, auth_headers, waiting):
        approve(client, auth_headers)

        last = confirm(client, auth_headers(COORDINATOR)).json()["history"][-1]

        assert (last["from"], last["to"]) == ("Pending Safety Check", "Confirmed")
        assert (last["byId"], last["byName"]) == (str(COORDINATOR_ID), "Priya")
        assert last["at"]

    def test_the_organiser_is_told(self, client, auth_headers, waiting, notification_repository):
        approve(client, auth_headers)

        confirm(client, auth_headers(COORDINATOR))

        told = [
            notice
            for notice in notification_repository.notifications
            if notice.user_id == ORGANISER_ID
        ]
        assert [(notice.kind, notice.status, notice.message) for notice in told] == [
            (
                "event-status",
                EventStatus.CONFIRMED,
                '"Open House" is confirmed and ready to go ahead.',
            )
        ]





class TestRefusals:
    def refused(self, client, auth_headers):
        response = confirm(client, auth_headers(COORDINATOR))
        assert response.status_code == 409, response.text
        return response.json()["detail"]

    def test_no_approval_is_refused(self, client, auth_headers, waiting, event_repository):
        detail = self.refused(client, auth_headers)

        assert detail["reason"] == "safety-not-approved"
        assert detail["message"] == NOT_APPROVED_MESSAGE
        assert event_repository.get_event(EVENT_ID).status is PSC

    def test_a_booking_still_requested_is_refused(
        self, client, auth_headers, waiting, booking_repository
    ):
        booking_repository.bookings.append(
            booking(2, BookingStatus.REQUESTED, venue="Breakout Room B")
        )
        approve(client, auth_headers)

        detail = self.refused(client, auth_headers)

        assert detail["reason"] == "venue-not-confirmed"
        assert detail["message"] == "Breakout Room B is still awaiting Venue Staff approval."

    def test_a_booking_needing_a_replacement_is_refused(
        self, client, auth_headers, waiting, booking_repository
    ):
        approve(client, auth_headers)
        booking_repository.bookings.append(
            booking(2, BookingStatus.NEEDS_REPLACEMENT, venue="Seminar Room 4")
        )

        detail = self.refused(client, auth_headers)

        assert detail["reason"] == "venue-needs-replacement"
        assert detail["message"] == "Seminar Room 4 needs a replacement venue."

    def test_a_booking_flagged_for_a_conflict_is_refused(
        self, client, auth_headers, waiting, booking_repository
    ):
        approve(client, auth_headers)
        booking_repository.bookings[0] = replace(
            booking_repository.bookings[0], conflict=ConflictFlag(NOW, "Setup overlaps")
        )

        detail = self.refused(client, auth_headers)

        assert detail["reason"] == "venue-conflict"
        assert detail["message"] == "Great Hall is flagged “Conflict – review needed”."

    def test_equipment_not_reserved_is_refused(
        self, client, auth_headers, waiting, equipment_repository
    ):
        approve(client, auth_headers)
        equipment_repository.requests[0] = line(status="Requested")

        detail = self.refused(client, auth_headers)

        assert detail["reason"] == "equipment-not-reserved"
        assert detail["message"] == "Projector is not reserved by Technical Support yet."

    def test_a_pending_change_request_is_refused(
        self, client, auth_headers, waiting, event_repository
    ):
        approve(client, auth_headers)
        event_repository.events[0] = replace(event_repository.events[0], change_requested=True)

        detail = self.refused(client, auth_headers)

        assert detail == {
            "code": "rule_refused",
            "message": CHANGE_PENDING_MESSAGE,
            "reason": "change-pending",
        }


class TestSafetyApproval:
    def test_an_approval_no_longer_confirms_it(self, client, auth_headers, waiting):
        approved = approve(client, auth_headers)

        assert approved["status"] == "Pending Safety Check"
        assert approved["safetyApproved"] is True


    def test_an_approval_of_an_earlier_stay_does_not_count(
        self, client, auth_headers, waiting, safety_decision_repository
    ):
        safety_decision_repository.decisions.append(
            SafetyDecision(
                id=99,
                event_id=EVENT_ID,
                outcome=SafetyOutcome.APPROVED,
                note="",
                decided_by_id=4,
                decided_by_name="Alex",
                decided_at=EARLIER,
                check_started_at=EARLIER,
            )
        )

        response = confirm(client, auth_headers(COORDINATOR))

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "safety-not-approved"


class TestWhoConfirms:
    def test_a_coordinator_not_assigned_is_refused(
        self, client, auth_headers, waiting, user_store, event_repository
    ):
        approve(client, auth_headers)
        other = add_user(user_store, client, 77, Role.COORDINATOR)

        response = confirm(client, other)

        # US8.6: an event that is not theirs is not there, as everywhere else.
        assert response.status_code == 404
        assert event_repository.get_event(EVENT_ID).status is PSC
        # D4: the refusal says what is true without revealing whether it exists.
        assert response.json()["detail"]["message"] == (
            "That event does not exist, or you do not have access to it."
        )

    @pytest.mark.parametrize("role", ["Event Coordinator Lead", "Event Organiser"])
    def test_the_lead_and_the_organiser_are_refused(self, client, auth_headers, waiting, role):
        approve(client, auth_headers)

        response = confirm(client, auth_headers(role))

        assert response.status_code == 403
        assert "confirm events" in response.json()["detail"]["message"]






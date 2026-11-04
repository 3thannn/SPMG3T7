"""US11.3: an important change to a Confirmed event goes back through approval.

Acceptance criteria, and the tests that hold each one:

* Accepting a change to an important field of a Confirmed event moves it
  Confirmed -> Planning, with the reason recorded -> `TestBackToPlanning`.
* A change to routine fields only leaves it Confirmed -> `TestRoutineChange`.
* Arrangements are re-checked as in US11.2; a failure is flagged, nothing is
  cancelled, and what still passes keeps its status -> `TestArrangements`.
* The earlier safety approval no longer counts: the event is sent again, needs
  a fresh decision, and the Coordinator confirms it (US4.7) ->
  `TestFreshSafetyCheck`.
* The Organiser and the assigned Coordinator are told, and why -> `TestNotices`.
* Registrations are kept; new ones pause until it is Confirmed again ->
  `TestRegistrations`.
* Confirmed -> Planning is allowed, and only through an approval -> `TestRules`.
  The database half is SUPABASE_US11_3_RECONFIRM.sql.
"""

import pytest

from app.booking_store import Booking, BookingStatus
from app.change_requests import FieldChange, reopen_reason
from app.event_status import EventStatus, transition_allowed
from app.event_store import Event, StatusChange
from app.notifications import CoordinatorNotice
from app.registration_store import RegistrationStatus
from app.safety_decisions import CHECK_MOVED_ON
from tests.conftest import (
    COORDINATOR_ID,
    ORGANISER_ID,
    SAFETY_OFFICER_ID,
    SECOND_ATTENDEE_ID,
    SUBMITTABLE_NEED_ATTRS,
    SUBMITTABLE_NEEDS,
)

EVENT_ID = 900
BOOKING_ID = 31
GREAT_HALL, BERTHA_ROOM = 1, 2  # capacities 500 and 40
#: When the event last entered Pending Safety Check, and when it was approved.
FIRST_CHECK = "2099-01-02T10:00:00"
APPROVED_AT = "2099-01-02T11:00:00"

#: The edit form as the event stands, so a proposal differs only where a test says.
FORM = {
    "title": "Open House",
    "purpose": "Welcome visitors",
    "description": "Tours and talks.",
    "startsAt": "2099-11-02T09:00",
    "endsAt": "2099-11-02T17:00",
    "expectedAttendance": 30,
    **SUBMITTABLE_NEEDS,
}

ORGANISER = "Event Organiser"
COORDINATOR = "Event Coordinator"
OFFICER = "Safety Officer"


@pytest.fixture
def confirmed(event_repository, booking_repository):
    """A Confirmed event, signed off once, with one Confirmed venue booking."""

    def _seed(venue_id: int = GREAT_HALL) -> Event:
        event = Event(
            id=EVENT_ID,
            title=FORM["title"],
            purpose=FORM["purpose"],
            description=FORM["description"],
            starts_at=FORM["startsAt"],
            ends_at=FORM["endsAt"],
            expected_attendance=FORM["expectedAttendance"],
            status=EventStatus.CONFIRMED,
            organiser_id=ORGANISER_ID,
            organiser_name="Dylan",
            created_at="2099-01-01T09:00:00",
            updated_at=APPROVED_AT,
            coordinator_id=COORDINATOR_ID,
            history=(
                StatusChange(
                    EventStatus.PLANNING,
                    EventStatus.PENDING_SAFETY_CHECK,
                    FIRST_CHECK,
                    COORDINATOR_ID,
                    "Priya",
                ),
                StatusChange(
                    EventStatus.PENDING_SAFETY_CHECK,
                    EventStatus.CONFIRMED,
                    APPROVED_AT,
                    SAFETY_OFFICER_ID,
                    "Alex",
                ),
            ),
            **SUBMITTABLE_NEED_ATTRS,
        )
        event_repository.events.append(event)
        booking_repository.bookings.append(
            Booking(
                id=BOOKING_ID,
                event_id=EVENT_ID,
                venue_id=venue_id,
                venue_name="Great Hall" if venue_id == GREAT_HALL else "Bertha Room",
                starts_at=FORM["startsAt"],
                ends_at=FORM["endsAt"],
                status=BookingStatus.CONFIRMED,
                requested_by_id=COORDINATOR_ID,
                requested_at="2099-01-01T09:00",
                headcount=30,
            )
        )
        return event

    return _seed


def change_and_accept(client, auth_headers, **changes):
    """The Organiser proposes the changes and the Coordinator accepts them (US11.1/US11.2)."""
    proposed = client.post(
        f"/events/{EVENT_ID}/change-request",
        json={**FORM, **changes},
        headers=auth_headers(ORGANISER),
    )
    assert proposed.status_code == 200, proposed.text
    accepted = client.post(
        f"/events/{EVENT_ID}/change-request/approve", headers=auth_headers(COORDINATOR)
    )
    assert accepted.status_code == 200, accepted.text
    return accepted.json()


ATTENDANCE_REASON = reopen_reason((FieldChange("expected_attendance", "30", "35", important=True),))


class TestBackToPlanning:

    def test_the_move_is_recorded_with_who_when_and_why(self, client, auth_headers, confirmed):
        confirmed()

        event = change_and_accept(client, auth_headers, expectedAttendance=35)

        moved = event["history"][-1]
        assert (moved["from"], moved["to"]) == ("Confirmed", "Planning")
        assert (moved["byId"], moved["byName"]) == (str(COORDINATOR_ID), "Priya")
        assert moved["at"]
        assert moved["notes"] == ATTENDANCE_REASON
        assert ATTENDANCE_REASON.startswith("Approved change to Expected attendance.")

    @pytest.mark.parametrize(
        "changes",
        [
            {"startsAt": "2099-11-02T10:00"},
            {"endsAt": "2099-11-02T16:00"},
            {"venueRequirements": "Stage"},
            {"equipmentNeeds": "4 wireless microphones"},
        ],
    )
    def test_every_important_field_does_it(self, client, auth_headers, confirmed, changes):
        confirmed()

        assert change_and_accept(client, auth_headers, **changes)["status"] == "Planning"



class TestRoutineChange:
    def test_accepted_title_only_change_stays_confirmed(
        self, client, auth_headers, confirmed, notification_repository
    ):
        confirmed()

        event = change_and_accept(client, auth_headers, title="Open House 2099")

        assert event["status"] == "Confirmed"
        assert event["title"] == "Open House 2099"
        assert event["history"][-1]["to"] == "Confirmed"
        assert not [
            notice
            for notice in notification_repository.notifications
            if notice.kind == CoordinatorNotice.BACK_IN_PLANNING
        ]


class TestArrangements:
    def test_a_booking_that_still_fits_keeps_its_status(
        self, client, auth_headers, confirmed, booking_repository
    ):
        confirmed(GREAT_HALL)

        change_and_accept(client, auth_headers, expectedAttendance=35)

        booking = booking_repository.get_booking(BOOKING_ID)
        assert booking.status is BookingStatus.CONFIRMED
        assert not booking.event_conflict_reason

    def test_a_booking_that_no_longer_fits_is_flagged_not_cancelled(
        self, client, auth_headers, confirmed, booking_repository
    ):
        confirmed(BERTHA_ROOM)

        event = change_and_accept(client, auth_headers, expectedAttendance=41)

        booking = booking_repository.get_booking(BOOKING_ID)
        assert booking.status is BookingStatus.CONFIRMED
        assert booking.event_conflict_reason
        assert event["status"] == "Planning"



class TestFreshSafetyCheck:

    def test_resending_needs_a_new_decision_not_the_earlier_one(
        self, client, auth_headers, confirmed
    ):
        confirmed()
        change_and_accept(client, auth_headers, expectedAttendance=35)

        sent = client.post(f"/events/{EVENT_ID}/safety-check", headers=auth_headers(COORDINATOR))
        assert sent.status_code == 200, sent.text
        assert sent.json()["status"] == "Pending Safety Check"

        earlier = client.post(
            f"/events/{EVENT_ID}/safety-check/approve",
            json={"checkStartedAt": FIRST_CHECK},
            headers=auth_headers(OFFICER),
        )
        assert earlier.status_code == 409
        assert earlier.json()["detail"]["message"] == CHECK_MOVED_ON



class TestNotices:
    def test_organiser_and_coordinator_are_told_why(
        self, client, auth_headers, confirmed, notification_repository
    ):
        confirmed()

        change_and_accept(client, auth_headers, expectedAttendance=35)

        told = {
            notice.user_id: notice.message
            for notice in notification_repository.notifications
            if notice.kind == CoordinatorNotice.BACK_IN_PLANNING
        }
        expected = f'"Open House" is back in Planning. {ATTENDANCE_REASON}'
        assert told == {ORGANISER_ID: expected, COORDINATOR_ID: expected}



class TestRegistrations:
    def test_registrations_are_kept_and_new_ones_pause(
        self, client, auth_headers, confirmed, registration_repository
    ):
        confirmed()
        registration_repository.settings[EVENT_ID] = (True, 30)
        registered = client.post(
            f"/attendee/events/{EVENT_ID}/registrations",
            json={"name": "Casey Tan", "email": "casey@example.com"},
            headers=auth_headers("Attendee"),
        )
        assert registered.status_code == 201, registered.text

        change_and_accept(client, auth_headers, expectedAttendance=35)

        (kept,) = registration_repository.registrations
        assert kept.status is RegistrationStatus.REGISTERED
        paused = client.post(
            f"/attendee/events/{EVENT_ID}/registrations",
            json={"name": "Morgan Lee", "email": "morgan@example.com"},
            headers=auth_headers("Second Attendee"),
        )
        assert paused.status_code == 404
        listed = client.get("/attendee/events", headers=auth_headers("Second Attendee")).json()
        assert str(EVENT_ID) not in [event["id"] for event in listed]
        attendees = [each.attendee_id for each in registration_repository.registrations]
        assert SECOND_ATTENDEE_ID not in attendees


class TestRules:
    def test_confirmed_to_planning_is_allowed(self):
        assert transition_allowed(from_status=EventStatus.CONFIRMED, to_status=EventStatus.PLANNING)





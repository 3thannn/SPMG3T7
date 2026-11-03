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
from app.change_requests import FieldChange, reopen_reason, reopens_planning
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
    def test_accepted_attendance_change_moves_it_to_planning(self, client, auth_headers, confirmed):
        confirmed()

        event = change_and_accept(client, auth_headers, expectedAttendance=35)

        assert event["status"] == "Planning"
        assert event["expectedAttendance"] == 35

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

    def test_a_rejected_change_leaves_it_confirmed(self, client, auth_headers, confirmed):
        confirmed()
        client.post(
            f"/events/{EVENT_ID}/change-request",
            json={**FORM, "expectedAttendance": 35},
            headers=auth_headers(ORGANISER),
        )

        rejected = client.post(
            f"/events/{EVENT_ID}/change-request/reject",
            json={"reason": "The hall is booked for 30."},
            headers=auth_headers(COORDINATOR),
        )

        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "Confirmed"
        assert rejected.json()["expectedAttendance"] == 30


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

    def test_a_flagged_booking_holds_back_the_safety_check(self, client, auth_headers, confirmed):
        confirmed(BERTHA_ROOM)
        change_and_accept(client, auth_headers, expectedAttendance=41)

        sent = client.post(f"/events/{EVENT_ID}/safety-check", headers=auth_headers(COORDINATOR))

        assert sent.status_code == 409
        assert sent.json()["detail"]["reason"] == "venue-conflict"


class TestFreshSafetyCheck:
    def test_the_safety_officer_cannot_confirm_it_from_planning(
        self, client, auth_headers, confirmed, event_repository
    ):
        confirmed()
        change_and_accept(client, auth_headers, expectedAttendance=35)

        approved = client.post(
            f"/events/{EVENT_ID}/safety-check/approve", headers=auth_headers(OFFICER)
        )

        # The Safety Officer reads only events waiting for their check (US4.4),
        # so one back in Planning is not there to approve at all.
        assert approved.status_code == 404
        assert event_repository.get_event(EVENT_ID).status is EventStatus.PLANNING

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

    def test_confirming_again_takes_the_new_approval(self, client, auth_headers, confirmed):
        confirmed()
        change_and_accept(client, auth_headers, expectedAttendance=35)
        client.post(f"/events/{EVENT_ID}/safety-check", headers=auth_headers(COORDINATOR))
        review = client.get(
            f"/events/{EVENT_ID}/safety-review", headers=auth_headers(OFFICER)
        ).json()

        approved = client.post(
            f"/events/{EVENT_ID}/safety-check/approve",
            json={"checkStartedAt": review["waitingSince"]},
            headers=auth_headers(OFFICER),
        )

        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "Pending Safety Check"
        assert review["waitingSince"] != FIRST_CHECK
        # US4.7: and then the Coordinator confirms it, on the new approval.
        confirmed = client.post(f"/events/{EVENT_ID}/confirm", headers=auth_headers(COORDINATOR))
        assert confirmed.status_code == 200, confirmed.text
        assert [(e["from"], e["to"]) for e in confirmed.json()["history"][-3:]] == [
            ("Confirmed", "Planning"),
            ("Planning", "Pending Safety Check"),
            ("Pending Safety Check", "Confirmed"),
        ]


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

    def test_the_organiser_still_hears_the_change_was_accepted(
        self, client, auth_headers, confirmed, notification_repository
    ):
        confirmed()

        change_and_accept(client, auth_headers, expectedAttendance=35)

        kinds = [
            notice.kind
            for notice in notification_repository.notifications
            if notice.user_id == ORGANISER_ID
        ]
        assert "change-accepted" in kinds


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

    def test_planning_still_cannot_jump_to_confirmed(self):
        assert not transition_allowed(
            from_status=EventStatus.PLANNING, to_status=EventStatus.CONFIRMED
        )

    @pytest.mark.parametrize(
        ("status", "important", "reopens"),
        [
            (EventStatus.CONFIRMED, True, True),
            (EventStatus.CONFIRMED, False, False),
            # Was False: an important change during the safety check left any
            # approval standing for different numbers (CODE_AUDIT.md D1).
            (EventStatus.PENDING_SAFETY_CHECK, True, True),
            (EventStatus.PENDING_SAFETY_CHECK, False, False),
            (EventStatus.PLANNING, True, False),
        ],
    )
    def test_only_an_important_change_once_the_safety_check_starts_reopens(
        self, status, important, reopens
    ):
        change = FieldChange("expected_attendance", "30", "35", important=important)

        assert reopens_planning(status=status, changes=(change,)) is reopens

    def test_the_reason_names_every_important_field_in_form_order(self):
        changes = (
            FieldChange("expected_attendance", "30", "35", important=True),
            FieldChange("name", "Open House", "Open Day", important=False),
            FieldChange("proposed_date", "2099-11-02T09:00", "2099-11-02T10:00", important=True),
            FieldChange("end_date", "2099-11-02T17:00", "2099-11-02T18:00", important=True),
        )

        assert reopen_reason(changes).startswith(
            "Approved changes to Starts, Ends and Expected attendance. "
        )

    def test_no_important_field_means_no_reason(self):
        routine = FieldChange("name", "Open House", "Open Day", important=False)

        assert reopen_reason((routine,)) == ""

"""US10.4: registered Attendees hear when their event's date, time or venue changes.

Acceptance criteria, and the tests that hold each one:

* An accepted change (US11.2/US11.3) to the date or time of an event with
  registrations tells every Attendee with an active registration the new date
  and time -> `TestNewTime`.
* Venue Staff confirming a replacement venue (US14.5/US12.4) on a registered
  event tells its Attendees the new venue -> `TestNewVenue`.
* Only Attendee-safe details: the event's name and the new date, time or
  venue, no notes or reasons (US20.1) -> `TestWhatTheyRead`.
* Withdrawn registrations are not told -> `TestNewTime`, `TestNewVenue`.
* US10.1's list and read/unread toggle -> `TestTheAttendeesList`.

The story's tests: `test_a_date_change_tells_only_the_two_registered`,
`test_a_title_change_tells_nobody` and
`test_a_confirmed_replacement_tells_the_registered`.
"""

from dataclasses import replace

import pytest

from app.booking_store import Booking, BookingStatus, is_replacement
from app.event_status import EventStatus
from app.event_store import Event
from app.notifications import EVENT_UPDATED, _when
from app.registration_store import Registration, RegistrationStatus
from tests.conftest import (
    ATTENDEE_ID,
    COORDINATOR_ID,
    ORGANISER_ID,
    SECOND_ATTENDEE_ID,
    SUBMITTABLE_NEED_ATTRS,
    SUBMITTABLE_NEEDS,
)

EVENT_ID = 970
#: Withdrew before the change, so is not told.
WITHDRAWN_ATTENDEE_ID = 22
GREAT_HALL, BERTHA_ROOM = 1, 2
REPLACED, REPLACEMENT = 51, 52

ORGANISER = "Event Organiser"
COORDINATOR = "Event Coordinator"
STAFF = "Venue Staff"

FORM = {
    "title": "Open House",
    "purpose": "Welcome visitors",
    "description": "Tours and talks.",
    "startsAt": "2099-11-02T09:00",
    "endsAt": "2099-11-02T17:00",
    "expectedAttendance": 30,
    **SUBMITTABLE_NEEDS,
}
NEW_TIME = '"Open House" has a new date and time: 3 Nov 2099, 10:00 to 18:00.'
NEW_VENUE = '"Open House" has a new venue: Bertha Room, Library, Level 3.'


def registration(registration_id, attendee_id, status=RegistrationStatus.REGISTERED):
    return Registration(
        id=registration_id,
        event_id=EVENT_ID,
        attendee_id=attendee_id,
        name=f"Attendee {attendee_id}",
        email=f"attendee{attendee_id}@example.com",
        status=status,
        created_at="2099-01-02T09:00:00",
        withdrawn_at="2099-01-03T09:00:00" if status is RegistrationStatus.WITHDRAWN else "",
    )


def booking(booking_id, venue_id, venue_name, status) -> Booking:
    return Booking(
        id=booking_id,
        event_id=EVENT_ID,
        venue_id=venue_id,
        venue_name=venue_name,
        starts_at=FORM["startsAt"],
        ends_at=FORM["endsAt"],
        status=status,
        requested_by_id=COORDINATOR_ID,
        requested_at="2099-01-01T09:00",
        headcount=30,
    )


@pytest.fixture
def registered(event_repository, registration_repository):
    """A Confirmed event with two Attendees registered and a third withdrawn."""
    event_repository.events.append(
        Event(
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
            updated_at="2099-01-02T12:00:00",
            coordinator_id=COORDINATOR_ID,
            **SUBMITTABLE_NEED_ATTRS,
        )
    )
    registration_repository.settings[EVENT_ID] = (True, 30)
    registration_repository.registrations.extend(
        [
            registration(1, ATTENDEE_ID),
            registration(2, SECOND_ATTENDEE_ID),
            registration(3, WITHDRAWN_ATTENDEE_ID, RegistrationStatus.WITHDRAWN),
        ]
    )


def change_and_accept(client, auth_headers, **changes):
    """The Organiser proposes the changes and the Coordinator accepts them (US11.1/US11.2)."""
    proposed = client.post(
        f"/events/{EVENT_ID}/change-request",
        json={**FORM, **changes, "note": "The hall is double-booked that morning."},
        headers=auth_headers(ORGANISER),
    )
    assert proposed.status_code == 200, proposed.text
    accepted = client.post(
        f"/events/{EVENT_ID}/change-request/approve", headers=auth_headers(COORDINATOR)
    )
    assert accepted.status_code == 200, accepted.text


def attendee_notices(notification_repository) -> dict[int, str]:
    return {
        notice.user_id: notice.message
        for notice in notification_repository.notifications
        if notice.kind == EVENT_UPDATED
    }


class TestNewTime:
    def test_a_date_change_tells_only_the_two_registered(
        self, client, auth_headers, registered, notification_repository
    ):
        change_and_accept(
            client, auth_headers, startsAt="2099-11-03T10:00", endsAt="2099-11-03T18:00"
        )

        assert attendee_notices(notification_repository) == {
            ATTENDEE_ID: NEW_TIME,
            SECOND_ATTENDEE_ID: NEW_TIME,
        }

    def test_a_time_change_alone_does_it_too(
        self, client, auth_headers, registered, notification_repository
    ):
        change_and_accept(client, auth_headers, endsAt="2099-11-02T18:00")

        assert set(attendee_notices(notification_repository).values()) == {
            '"Open House" has a new date and time: 2 Nov 2099, 09:00 to 18:00.'
        }

    def test_a_title_change_tells_nobody(
        self, client, auth_headers, registered, notification_repository
    ):
        change_and_accept(client, auth_headers, title="Open House 2099")

        assert attendee_notices(notification_repository) == {}

    def test_a_rejected_date_change_tells_nobody(
        self, client, auth_headers, registered, notification_repository
    ):
        client.post(
            f"/events/{EVENT_ID}/change-request",
            json={**FORM, "startsAt": "2099-11-03T10:00", "endsAt": "2099-11-03T18:00"},
            headers=auth_headers(ORGANISER),
        )

        client.post(
            f"/events/{EVENT_ID}/change-request/reject",
            json={"reason": "The new day clashes with exams."},
            headers=auth_headers(COORDINATOR),
        )

        assert attendee_notices(notification_repository) == {}

    def test_an_event_without_registrations_tells_nobody(
        self, client, auth_headers, registered, registration_repository, notification_repository
    ):
        registration_repository.registrations.clear()

        change_and_accept(client, auth_headers, startsAt="2099-11-02T10:00")

        assert attendee_notices(notification_repository) == {}


@pytest.fixture
def replacement_requested(registered, event_repository, booking_repository):
    """Back in Planning (US12.4), the Great Hall replaced by a request for the Bertha Room."""
    event_repository.events[-1] = replace(event_repository.events[-1], status=EventStatus.PLANNING)
    booking_repository.bookings.extend(
        [
            booking(REPLACED, GREAT_HALL, "Great Hall", BookingStatus.REPLACED),
            booking(REPLACEMENT, BERTHA_ROOM, "Bertha Room", BookingStatus.REQUESTED),
        ]
    )


def approve(client, auth_headers, booking_id=REPLACEMENT):
    approved = client.post(f"/booking-requests/{booking_id}/approve", headers=auth_headers(STAFF))
    assert approved.status_code == 200, approved.text


class TestNewVenue:
    def test_a_confirmed_replacement_tells_the_registered(
        self, client, auth_headers, replacement_requested, notification_repository
    ):
        approve(client, auth_headers)

        assert attendee_notices(notification_repository) == {
            ATTENDEE_ID: NEW_VENUE,
            SECOND_ATTENDEE_ID: NEW_VENUE,
        }

    def test_a_venue_that_replaced_nothing_tells_nobody(
        self, client, auth_headers, registered, booking_repository, notification_repository
    ):
        booking_repository.bookings.append(
            booking(REPLACEMENT, BERTHA_ROOM, "Bertha Room", BookingStatus.REQUESTED)
        )

        approve(client, auth_headers)

        assert attendee_notices(notification_repository) == {}

    def test_a_rejected_replacement_tells_nobody(
        self, client, auth_headers, replacement_requested, notification_repository
    ):
        client.post(
            f"/booking-requests/{REPLACEMENT}/reject",
            json={"reason": "Closed for exams."},
            headers=auth_headers(STAFF),
        )

        assert attendee_notices(notification_repository) == {}


class TestWhatTheyRead:
    def test_no_note_or_reason_reaches_an_attendee(
        self, client, auth_headers, registered, notification_repository
    ):
        change_and_accept(client, auth_headers, startsAt="2099-11-02T10:00")

        for message in attendee_notices(notification_repository).values():
            assert "double-booked" not in message
            assert "Planning" not in message
            assert "safety" not in message.lower()

    def test_an_event_running_past_midnight_names_both_days(self):
        event = Event(
            id=1,
            title="Night Market",
            purpose="",
            description="",
            starts_at="2099-11-02T18:00:00",
            ends_at="2099-11-03T01:30:00",
            expected_attendance=1,
            status=EventStatus.CONFIRMED,
            organiser_id=ORGANISER_ID,
            organiser_name="",
            created_at="",
            updated_at="",
        )

        assert _when(event) == "2 Nov 2099, 18:00 to 3 Nov 2099, 01:30"

    def test_unreadable_times_are_shown_as_they_are(self):
        event = Event(
            id=1,
            title="",
            purpose="",
            description="",
            starts_at="soon",
            ends_at="later",
            expected_attendance=1,
            status=EventStatus.CONFIRMED,
            organiser_id=ORGANISER_ID,
            organiser_name="",
            created_at="",
            updated_at="",
        )

        assert _when(event) == "soon to later"


class TestTheAttendeesList:
    def test_the_attendee_reads_it_and_marks_it_read(self, client, auth_headers, registered):
        change_and_accept(
            client, auth_headers, startsAt="2099-11-03T10:00", endsAt="2099-11-03T18:00"
        )
        attendee = auth_headers("Attendee")

        [notice] = client.get("/notifications", headers=attendee).json()
        assert (notice["kind"], notice["status"], notice["message"], notice["read"]) == (
            EVENT_UPDATED,
            None,
            NEW_TIME,
            False,
        )

        marked = client.patch(
            f"/notifications/{notice['id']}", json={"read": True}, headers=attendee
        )
        assert marked.json()["read"] is True


class TestBestEffort:
    def test_an_unreadable_registration_list_does_not_fail_the_approval(
        self, client, auth_headers, registered, registration_repository, monkeypatch
    ):
        def broken(_event_id):
            raise RuntimeError("registrations table unreachable")

        monkeypatch.setattr(registration_repository, "list_for_event", broken)

        change_and_accept(client, auth_headers, startsAt="2099-11-02T10:00")

    def test_a_failed_notice_does_not_fail_the_approval(
        self, client, auth_headers, registered, notification_repository, monkeypatch
    ):
        def broken(**_kwargs):
            raise RuntimeError("kind check rejected the row")

        monkeypatch.setattr(notification_repository, "create_notice", broken)

        change_and_accept(client, auth_headers, startsAt="2099-11-02T10:00")


class TestIsReplacement:
    def test_a_replaced_booking_at_the_same_times_on_the_same_event(self):
        new = booking(REPLACEMENT, BERTHA_ROOM, "Bertha Room", BookingStatus.CONFIRMED)
        old = booking(REPLACED, GREAT_HALL, "Great Hall", BookingStatus.REPLACED)

        assert is_replacement(new, [old, new])

    @pytest.mark.parametrize(
        "other",
        [
            booking(REPLACED, GREAT_HALL, "Great Hall", BookingStatus.CANCELLED),
            replace(
                booking(REPLACED, GREAT_HALL, "Great Hall", BookingStatus.REPLACED),
                starts_at="2099-11-02T10:00",
            ),
            replace(
                booking(REPLACED, GREAT_HALL, "Great Hall", BookingStatus.REPLACED),
                event_id=EVENT_ID + 1,
            ),
        ],
        ids=["not-replaced", "other-times", "other-event"],
    )
    def test_anything_else_is_not(self, other):
        new = booking(REPLACEMENT, BERTHA_ROOM, "Bertha Room", BookingStatus.CONFIRMED)

        assert not is_replacement(new, [other, new])

"""G13: the Week 1 notifications that had no story.

The Week 1 briefing lists who is told what. Four triggers were not built, and
are now:

* a venue booking is requested -> every Venue Staff member (`TestBookingRequested`);
* an event opens for registration -> every Attendee, and closes -> those
  registered (`TestRegistrationOpensAndCloses`);
* an Attendee withdraws, freeing a place -> the Organiser and the Coordinator
  (`TestAttendeeWithdraws`).

Each notice is best effort, like every other: the action it reports has
already succeeded.
"""

from app.event_status import EventStatus
from app.notifications import (
    REGISTRATION_CLOSED,
    REGISTRATION_OPENED,
    CoordinatorNotice,
)
from tests.conftest import (
    ATTENDEE_ID,
    COORDINATOR_ID,
    ORGANISER_ID,
    SECOND_ATTENDEE_ID,
    VENUE_STAFF_ID,
)
from tests.test_registration_us20_1 import (
    ATTENDEE,
    COORDINATOR,
    ORGANISER,
    open_registration,
    put_settings,
    register,
    seed_event,
)
from tests.test_registration_us20_2 import withdraw
from tests.test_venue_bookings import request
from tests.test_venue_bookings import seed_event as seed_booking_event


def told(notification_repository, kind: str) -> list[tuple[int, str]]:
    return [
        (item.user_id, item.message)
        for item in notification_repository.notifications
        if item.kind == kind
    ]


class TestBookingRequested:
    def test_venue_staff_are_told_a_request_is_waiting(
        self, client, auth_headers, event_repository, notification_repository
    ):
        seed_booking_event(event_repository, status=EventStatus.PLANNING)

        response = request(client, auth_headers(COORDINATOR))

        assert response.status_code == 201, response.text
        assert told(notification_repository, CoordinatorNotice.BOOKING_REQUESTED) == [
            (
                VENUE_STAFF_ID,
                'Great Hall was requested for "Faculty Welcome Night" on 02 Nov 2027, 09:00. '
                "It is waiting for your approval.",
            )
        ]

    def test_a_refused_request_tells_nobody(
        self, client, auth_headers, event_repository, notification_repository
    ):
        seed_booking_event(event_repository, status=EventStatus.PLANNING)

        request(client, auth_headers(COORDINATOR), startsAt=None)

        assert told(notification_repository, CoordinatorNotice.BOOKING_REQUESTED) == []


class TestRegistrationOpensAndCloses:
    def test_opening_tells_every_attendee(
        self, client, auth_headers, event_repository, notification_repository
    ):
        seed_event(event_repository)

        response = put_settings(client, auth_headers(COORDINATOR), {"open": True, "capacity": 30})

        assert response.status_code == 200, response.text
        assert told(notification_repository, REGISTRATION_OPENED) == [
            (ATTENDEE_ID, '"Open House" is open for registration.'),
            (SECOND_ATTENDEE_ID, '"Open House" is open for registration.'),
        ]

    def test_saving_it_open_again_tells_nobody_twice(
        self, client, auth_headers, event_repository, registration_repository,
        notification_repository,
    ):
        seed_event(event_repository)
        open_registration(registration_repository)

        put_settings(client, auth_headers(ORGANISER), {"open": True, "capacity": 40})

        assert told(notification_repository, REGISTRATION_OPENED) == []

    def test_closing_tells_those_registered(
        self, client, auth_headers, event_repository, registration_repository,
        notification_repository,
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        register(client, auth_headers(ATTENDEE))

        put_settings(client, auth_headers(COORDINATOR), {"open": False})

        assert told(notification_repository, REGISTRATION_CLOSED) == [
            (ATTENDEE_ID, 'Registration for "Open House" has closed. Your place is kept.')
        ]


class TestAttendeeWithdraws:
    def test_the_organiser_and_coordinator_are_told_a_place_is_free(
        self, client, auth_headers, event_repository, registration_repository,
        notification_repository,
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        registration_id = register(client, auth_headers(ATTENDEE)).json()["id"]

        response = withdraw(client, auth_headers(ATTENDEE), registration_id)

        assert response.status_code == 200, response.text
        message = 'An Attendee withdrew from "Open House", so a place is free again.'
        assert told(notification_repository, CoordinatorNotice.ATTENDEE_WITHDREW) == [
            (COORDINATOR_ID, message),
            (ORGANISER_ID, message),
        ]

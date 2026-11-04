"""US20.1: an Attendee registers for a Confirmed event.

Acceptance criteria, and the tests that hold each one:

* The assigned Coordinator can turn registration on for an event and set a
  registration capacity (a whole number of at least 1, defaulting to the
  expected attendance) -> `TestTurningRegistrationOn`, `TestTheCapacity`,
  `TestWhoMaySetIt`, `TestWhichEvents`, `TestTheRule`.
* Attendees see Confirmed events with registration turned on: name, date and
  time, venues and places left. Internal planning information is never shown
  -> `TestWhatAttendeesSee`.
* An Attendee registers with a name and an email, both required. Only one
  active registration per Attendee per event -> `TestRegistering`,
  `TestOnePerAttendee`.
* At capacity, registering is refused with "Event is full". Two Attendees after
  the last place at once: only one succeeds -> `TestCapacityIsEnforced`. The
  database half of that is test_registration_db.py (opt-in) and
  TEST_US20_1_REGISTRATION.sql.
* The Coordinator and the Organiser are told when the event becomes full
  (US10.2) -> `TestFullNotice`.
"""

import threading

import pytest

from app.booking_store import Booking, BookingStatus
from app.event_status import EventStatus
from app.event_store import Event
from app.notifications import CoordinatorNotice
from app.permissions import Permission, Role, denial_message
from app.registration_store import RegisterOutcome
from tests.conftest import (
    ATTENDEE_ID,
    COORDINATOR_ID,
    ORGANISER_ID,
    SECOND_ATTENDEE_ID,
    SUBMITTABLE_NEED_ATTRS,
)
from tests.test_change_requests import add_user

EVENT_ID = 950
OTHER_EVENT_ID = 951
STARTS = "2099-11-02T09:00"
ENDS = "2099-11-02T17:00"
ATTENDEE = "Attendee"
SECOND = "Second Attendee"
COORDINATOR = "Event Coordinator"
ORGANISER = "Event Organiser"


def seed_event(
    event_repository,
    status=EventStatus.CONFIRMED,
    *,
    event_id=EVENT_ID,
    title="Open House",
    starts_at=STARTS,
    coordinator_id=COORDINATOR_ID,
    attendance: int | None = 30,
):
    event = Event(
        id=event_id,
        title=title,
        purpose="Welcome visitors",
        description="Tours and talks. Internal: VIP list in the shared drive.",
        starts_at=starts_at,
        ends_at=ENDS,
        expected_attendance=attendance,
        status=status,
        organiser_id=ORGANISER_ID,
        organiser_name="Dylan",
        created_at="2099-01-01T09:00",
        updated_at="2099-01-01T09:00",
        coordinator_id=coordinator_id,
        **SUBMITTABLE_NEED_ATTRS,
    )
    event_repository.events.append(event)
    return event


def open_registration(registration_repository, capacity=30, *, event_id=EVENT_ID):
    registration_repository.settings[event_id] = (True, capacity)


def booking(booking_id, status, venue_name, *, event_id=EVENT_ID, venue_id=1):
    return Booking(
        id=booking_id,
        event_id=event_id,
        venue_id=venue_id,
        venue_name=venue_name,
        starts_at=STARTS,
        ends_at=ENDS,
        status=status,
        requested_by_id=COORDINATOR_ID,
        requested_at="2099-01-01T09:00",
        headcount=30,
    )


def put_settings(client, headers, payload, *, event_id=EVENT_ID):
    return client.put(f"/events/{event_id}/registration", json=payload, headers=headers)


def get_settings(client, headers, *, event_id=EVENT_ID):
    return client.get(f"/events/{event_id}/registration", headers=headers)


def register(client, headers, *, name="Casey Tan", email="casey@example.com", event_id=EVENT_ID):
    return client.post(
        f"/attendee/events/{event_id}/registrations",
        json={"name": name, "email": email},
        headers=headers,
    )


def open_events(client, headers):
    return client.get("/attendee/events", headers=headers)


def full_notices(notification_repository):
    return [
        notice
        for notice in notification_repository.notifications
        if notice.kind == CoordinatorNotice.EVENT_FULL
    ]




class TestTurningRegistrationOn:
    """AC1: the assigned Coordinator turns it on and sets the capacity."""

    def test_the_assigned_coordinator_turns_it_on_with_a_capacity(
        self, client, auth_headers, event_repository
    ):
        seed_event(event_repository)

        response = put_settings(client, auth_headers(COORDINATOR), {"open": True, "capacity": 50})

        assert response.status_code == 200, response.text
        assert response.json() == {
            "eventId": str(EVENT_ID),
            "open": True,
            "capacity": 50,
            "registered": 0,
            "placesLeft": 50,
            "defaultCapacity": 30,
        }

    def test_the_capacity_defaults_to_the_expected_attendance(
        self, client, auth_headers, event_repository
    ):
        seed_event(event_repository, attendance=120)

        response = put_settings(client, auth_headers(COORDINATOR), {"open": True})

        assert response.status_code == 200, response.text
        assert response.json()["capacity"] == 120






class TestTheCapacity:
    """AC1: a whole number, at least 1."""

    @pytest.mark.parametrize("capacity", [0, -1, 1.5, "abc", True, "1e3"])
    def test_anything_but_a_whole_number_of_at_least_one_is_refused(
        self, client, auth_headers, event_repository, capacity
    ):
        seed_event(event_repository)

        response = put_settings(
            client, auth_headers(COORDINATOR), {"open": True, "capacity": capacity}
        )

        assert response.status_code == 400
        assert response.json()["detail"] == {
            "code": "invalid_registration",
            "message": "Give the capacity as a whole number of places, at least 1.",
        }










class TestWhoMaySetIt:
    @pytest.mark.parametrize(
        "role",
        ["Event Coordinator Lead", "Venue Staff", "Safety Officer", ATTENDEE],
    )
    def test_no_other_role_may_change_it(self, client, auth_headers, event_repository, role):
        seed_event(event_repository)

        response = put_settings(client, auth_headers(role), {"open": True})

        assert response.status_code == 403
        assert response.json()["detail"]["message"] == denial_message(
            Role(role), Permission.REGISTRATION_MANAGE
        )

    def test_the_owning_organiser_opens_and_closes_it(
        self, client, auth_headers, event_repository
    ):
        """D3 (CODE_AUDIT.md): "organiser control timing" and "closure is based on
        Organiser discretion" (Week 4 answers); the Week 4 instructions do not say
        who enables registration. The assigned Coordinator keeps the switch too."""
        seed_event(event_repository)

        opened = put_settings(client, auth_headers(ORGANISER), {"open": True, "capacity": 40})
        closed = put_settings(client, auth_headers(ORGANISER), {"open": False})

        assert opened.status_code == 200, opened.text
        assert (opened.json()["open"], opened.json()["capacity"]) == (True, 40)
        assert closed.status_code == 200, closed.text
        assert (closed.json()["open"], closed.json()["capacity"]) == (False, 40)

    def test_another_organiser_is_told_it_does_not_exist(
        self, client, auth_headers, event_repository, user_store
    ):
        seed_event(event_repository)
        other = add_user(user_store, client, 77, Role.ORGANISER)

        response = put_settings(client, other, {"open": True})

        assert response.status_code == 404








class TestWhatAttendeesSee:
    """AC2: Confirmed events taking registrations, and only what an Attendee needs."""

    def test_a_confirmed_event_taking_registrations_is_listed(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 30)

        response = open_events(client, auth_headers(ATTENDEE))

        assert response.status_code == 200, response.text
        assert response.json() == [
            {
                "id": str(EVENT_ID),
                "title": "Open House",
                "startsAt": STARTS,
                "endsAt": ENDS,
                "venues": [],
                "placesLeft": 30,
                "registered": False,
            }
        ]

    def test_nothing_of_the_planning_is_shown(
        self, client, auth_headers, event_repository, registration_repository, booking_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        booking_repository.bookings.append(booking(1, BookingStatus.CONFIRMED, "Great Hall"))

        listed = open_events(client, auth_headers(ATTENDEE)).json()[0]
        one = client.get(f"/attendee/events/{EVENT_ID}", headers=auth_headers(ATTENDEE)).json()

        for shown in (listed, one):
            assert set(shown) == {
                "id", "title", "startsAt", "endsAt", "venues", "placesLeft", "registered",
            }
            assert "Internal" not in str(shown)
            assert "Dylan" not in str(shown) and "Priya" not in str(shown)

    @pytest.mark.parametrize(
        ("status", "is_open"),
        [
            (EventStatus.PLANNING, True),
            (EventStatus.PENDING_SAFETY_CHECK, True),
            (EventStatus.COMPLETED, True),
            (EventStatus.CANCELLED, True),
            (EventStatus.CONFIRMED, False),
        ],
    )
    def test_anything_else_is_not_listed(
        self, client, auth_headers, event_repository, registration_repository, status, is_open
    ):
        seed_event(event_repository, status)
        registration_repository.settings[EVENT_ID] = (is_open, 30)

        assert open_events(client, auth_headers(ATTENDEE)).json() == []
        assert client.get(
            f"/attendee/events/{EVENT_ID}", headers=auth_headers(ATTENDEE)
        ).status_code == 404












class TestRegistering:
    """AC3: a name and an email, both required."""

    def test_an_attendee_registers_with_a_name_and_an_email(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)

        response = register(client, auth_headers(ATTENDEE))

        assert response.status_code == 201, response.text
        body = response.json()
        assert {key: body[key] for key in ("eventId", "name", "email", "status")} == {
            "eventId": str(EVENT_ID),
            "name": "Casey Tan",
            "email": "casey@example.com",
            "status": "Registered",
        }
        assert body["id"] and body["createdAt"]
        stored = registration_repository.registrations
        assert [(item.event_id, item.attendee_id) for item in stored] == [(EVENT_ID, ATTENDEE_ID)]


    @pytest.mark.parametrize("name", ["", "   "])
    def test_a_name_is_required(
        self, client, auth_headers, event_repository, registration_repository, name
    ):
        seed_event(event_repository)
        open_registration(registration_repository)

        response = register(client, auth_headers(ATTENDEE), name=name)

        assert response.status_code == 400
        assert response.json()["detail"] == {
            "code": "invalid_registration",
            "message": "Give your name.",
        }
        assert registration_repository.registrations == []

    @pytest.mark.parametrize("email", ["", "   "])
    def test_an_email_is_required(
        self, client, auth_headers, event_repository, registration_repository, email
    ):
        seed_event(event_repository)
        open_registration(registration_repository)

        response = register(client, auth_headers(ATTENDEE), email=email)

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == "Give your email address."







class TestOnePerAttendee:
    """AC3: one active registration per Attendee per event."""

    def test_registering_twice_is_refused_with_the_reason(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        headers = auth_headers(ATTENDEE)
        register(client, headers)

        again = register(client, headers, name="Casey T", email="other@example.com")

        assert again.status_code == 409
        assert again.json()["detail"]["reason"] == "already-registered"
        assert again.json()["detail"]["message"] == "You are already registered for this event."
        assert len(registration_repository.registrations) == 1





class TestCapacityIsEnforced:
    """AC4: no more registrations than places, even two at once."""

    def test_the_last_place_is_taken_and_the_next_is_refused(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 1)

        last = register(client, auth_headers(ATTENDEE))
        refused = register(
            client, auth_headers(SECOND), name="Morgan Lee", email="morgan@example.com"
        )

        assert last.status_code == 201, last.text
        assert refused.status_code == 409
        assert refused.json()["detail"] == {
            "code": "rule_refused",
            "message": "Event is full.",
            "reason": "event-full",
        }
        assert len(registration_repository.registrations) == 1




    def test_two_at_once_for_the_last_place_only_one_gets_it(
        self, event_repository, registration_repository
    ):
        """The store holds one lock, as the database locks the event row."""
        seed_event(event_repository)
        for round_ in range(25):
            registration_repository.registrations.clear()
            open_registration(registration_repository, 1)
            start = threading.Barrier(2)
            outcomes: list[RegisterOutcome] = []

            def attempt(attendee_id, start=start, outcomes=outcomes):
                start.wait()
                result = registration_repository.register(
                    EVENT_ID, attendee_id=attendee_id, name="A", email="a@example.com"
                )
                outcomes.append(result.outcome)

            threads = [
                threading.Thread(target=attempt, args=(person,))
                for person in (ATTENDEE_ID, SECOND_ATTENDEE_ID)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            assert sorted(outcomes) == sorted(
                [RegisterOutcome.REGISTERED, RegisterOutcome.FULL]
            ), f"round {round_}"
            assert len(registration_repository.registrations) == 1


class TestFullNotice:
    """AC5: the Coordinator and the Organiser hear when the last place goes."""

    def test_both_are_told_once_when_the_last_place_is_taken(
        self, client, auth_headers, event_repository, registration_repository,
        notification_repository,
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 2)

        register(client, auth_headers(ATTENDEE))
        assert full_notices(notification_repository) == []

        register(client, auth_headers(SECOND), name="Morgan Lee", email="morgan@example.com")

        told = full_notices(notification_repository)
        assert sorted(notice.user_id for notice in told) == sorted([COORDINATOR_ID, ORGANISER_ID])
        assert {notice.message for notice in told} == {
            '"Open House" is full: all 2 places are taken.'
        }
        assert {(notice.event_id, notice.status) for notice in told} == {(EVENT_ID, None)}












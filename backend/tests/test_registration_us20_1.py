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


import pytest

from app.booking_store import Booking
from app.event_status import EventStatus
from app.event_store import Event
from app.notifications import CoordinatorNotice
from app.registration_store import SETTABLE
from app.registrations import (
    SETTINGS_REFUSAL_MESSAGES,
    SettingsRefusal,
    check_settings,
    settings_refusal_message,
)
from tests.conftest import (
    COORDINATOR_ID,
    ORGANISER_ID,
    SUBMITTABLE_NEED_ATTRS,
)

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


class TestTheRule:
    @pytest.mark.parametrize("status", sorted(SETTABLE))
    def test_from_approval_until_the_event_is_over(self, status):
        assert check_settings(status=status) is None

    @pytest.mark.parametrize(
        "status", [EventStatus.DRAFT, EventStatus.SUBMITTED, EventStatus.UNDER_REVIEW]
    )
    def test_not_before_approval(self, status):
        assert check_settings(status=status) is SettingsRefusal.NOT_APPROVED

    @pytest.mark.parametrize(
        "status", [EventStatus.COMPLETED, EventStatus.CANCELLED, EventStatus.REJECTED]
    )
    def test_not_once_the_event_is_closed(self, status):
        assert check_settings(status=status) is SettingsRefusal.EVENT_CLOSED

    def test_every_status_has_an_answer(self):
        covered = set(SETTABLE) | {
            status for status in EventStatus if check_settings(status=status) is not None
        }
        assert covered == set(EventStatus)

    @pytest.mark.parametrize("reason", list(SettingsRefusal))
    def test_every_refusal_explains_itself(self, reason):
        assert settings_refusal_message(reason) == SETTINGS_REFUSAL_MESSAGES[reason]
        assert settings_refusal_message(reason).endswith(".")


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

    def test_it_is_off_until_turned_on(self, client, auth_headers, event_repository):
        seed_event(event_repository)

        body = get_settings(client, auth_headers(COORDINATOR)).json()

        assert body == {
            "eventId": str(EVENT_ID),
            "open": False,
            "capacity": None,
            "registered": 0,
            "placesLeft": None,
            "defaultCapacity": 30,
        }

    def test_turning_it_off_keeps_the_capacity_for_next_time(
        self, client, auth_headers, event_repository
    ):
        seed_event(event_repository)
        headers = auth_headers(COORDINATOR)
        put_settings(client, headers, {"open": True, "capacity": 50})

        off = put_settings(client, headers, {"open": False})
        back_on = put_settings(client, headers, {"open": True})

        assert (off.json()["open"], off.json()["capacity"]) == (False, 50)
        # The stored 50, not the expected attendance of 30.
        assert (back_on.json()["open"], back_on.json()["capacity"]) == (True, 50)

    def test_it_can_be_opened_before_the_event_is_confirmed(
        self, client, auth_headers, event_repository
    ):
        seed_event(event_repository, EventStatus.PLANNING)

        response = put_settings(client, auth_headers(COORDINATOR), {"open": True})

        assert response.status_code == 200, response.text
        assert response.json()["open"] is True

    @pytest.mark.parametrize("role", [ORGANISER, COORDINATOR, "Event Coordinator Lead"])
    def test_anyone_who_can_open_the_event_reads_the_settings(
        self, client, auth_headers, event_repository, registration_repository, role
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 2)
        register(client, auth_headers(ATTENDEE))

        response = get_settings(client, auth_headers(role))

        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["open"], body["capacity"], body["registered"], body["placesLeft"]) == (
            True,
            2,
            1,
            1,
        )


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

    def test_an_empty_box_is_no_capacity_so_the_attendance_is_used(
        self, client, auth_headers, event_repository
    ):
        seed_event(event_repository)

        response = put_settings(client, auth_headers(COORDINATOR), {"open": True, "capacity": ""})

        assert response.status_code == 200, response.text
        assert response.json()["capacity"] == 30

    @pytest.mark.parametrize(
        ("sent", "stored"),
        [(1, 1), ("12", 12), (12.0, 12), (2_147_483_647, 2_147_483_647)],
    )
    def test_whole_numbers_are_taken_however_they_are_sent(
        self, client, auth_headers, event_repository, sent, stored
    ):
        seed_event(event_repository)

        response = put_settings(client, auth_headers(COORDINATOR), {"open": True, "capacity": sent})

        assert response.status_code == 200, response.text
        assert response.json()["capacity"] == stored

    def test_one_more_than_the_column_holds_is_refused(
        self, client, auth_headers, event_repository
    ):
        seed_event(event_repository)

        response = put_settings(
            client, auth_headers(COORDINATOR), {"open": True, "capacity": 2_147_483_648}
        )

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == (
            "That capacity is larger than this system can hold."
        )

    def test_with_no_attendance_a_capacity_must_be_given(
        self, client, auth_headers, event_repository
    ):
        seed_event(event_repository, attendance=None)

        response = put_settings(client, auth_headers(COORDINATOR), {"open": True})

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == (
            "Give a capacity: this event has no expected attendance to start from."
        )

    def test_turning_it_off_needs_no_capacity(self, client, auth_headers, event_repository):
        seed_event(event_repository, attendance=None)

        response = put_settings(client, auth_headers(COORDINATOR), {"open": False})

        assert response.status_code == 200, response.text
        assert (response.json()["open"], response.json()["capacity"]) == (False, None)

    def test_it_cannot_go_below_the_places_taken(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 5)
        register(client, auth_headers(ATTENDEE))
        register(client, auth_headers(SECOND), name="Morgan Lee", email="morgan@example.com")

        response = put_settings(client, auth_headers(COORDINATOR), {"open": True, "capacity": 1})

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["reason"] == "below-registered"
        assert detail["message"] == (
            "2 people have already registered, so the capacity cannot be less than 2."
        )
        assert registration_repository.settings_for(EVENT_ID).capacity == 5


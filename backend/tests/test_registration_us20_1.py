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
from dataclasses import replace

import pytest

from app.booking_store import Booking, BookingStatus
from app.event_status import EventStatus
from app.event_store import Event
from app.notifications import CoordinatorNotice
from app.permissions import Permission, Role, denial_message, roles_with
from app.registration_store import RegisterOutcome
from app.registrations import (
    SettingsRefusal,
    _tell_full,
    check_settings,
)
from tests.conftest import (
    ATTENDEE_ID,
    COORDINATOR_ID,
    ORGANISER_ID,
    SECOND_ATTENDEE_ID,
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

    @pytest.mark.parametrize(
        "status", [EventStatus.DRAFT, EventStatus.SUBMITTED, EventStatus.UNDER_REVIEW]
    )
    def test_not_before_approval(self, status):
        assert check_settings(status=status) is SettingsRefusal.NOT_APPROVED





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


    def test_exactly_the_places_taken_is_allowed_and_leaves_none(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 5)
        register(client, auth_headers(ATTENDEE))
        register(client, auth_headers(SECOND), name="Morgan Lee", email="morgan@example.com")

        response = put_settings(client, auth_headers(COORDINATOR), {"open": True, "capacity": 2})

        assert response.status_code == 200, response.text
        assert (response.json()["capacity"], response.json()["placesLeft"]) == (2, 0)


class TestWhoMaySetIt:
    @pytest.mark.parametrize(
        "role",
        [ORGANISER, "Event Coordinator Lead", "Venue Staff", "Safety Officer", ATTENDEE],
    )
    def test_no_other_role_may_change_it(self, client, auth_headers, event_repository, role):
        seed_event(event_repository)

        response = put_settings(client, auth_headers(role), {"open": True})

        assert response.status_code == 403
        assert response.json()["detail"]["message"] == denial_message(
            Role(role), Permission.REGISTRATION_MANAGE
        )

    def test_the_denial_names_who_may(self):
        assert denial_message(Role.ORGANISER, Permission.REGISTRATION_MANAGE) == (
            "The Event Organiser role cannot open or close registration for events. "
            "That is available to: Event Coordinator."
        )

    def test_a_coordinator_not_assigned_to_the_event_gets_not_found(
        self, client, auth_headers, event_repository
    ):
        seed_event(event_repository, coordinator_id=None)
        headers = auth_headers(COORDINATOR)

        assert put_settings(client, headers, {"open": True}).status_code == 404
        assert get_settings(client, headers).status_code == 404


    def test_signed_out_is_asked_to_sign_in(self, client, event_repository):
        seed_event(event_repository)
        refused = client.put(f"/events/{EVENT_ID}/registration", json={"open": True})
        assert refused.status_code == 401
        assert client.get(f"/events/{EVENT_ID}/registration").status_code == 401


class TestWhichEvents:
    @pytest.mark.parametrize("status", [EventStatus.SUBMITTED, EventStatus.UNDER_REVIEW])
    def test_not_before_approval(self, client, auth_headers, event_repository, status):
        seed_event(event_repository, status)

        response = put_settings(client, auth_headers(COORDINATOR), {"open": True})

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "not-approved"
        assert response.json()["detail"]["message"] == (
            "Approve this event before opening registration."
        )

    @pytest.mark.parametrize("status", [EventStatus.COMPLETED, EventStatus.REJECTED])
    def test_not_once_it_is_over(self, client, auth_headers, event_repository, status):
        seed_event(event_repository, status)

        response = put_settings(client, auth_headers(COORDINATOR), {"open": True})

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "event-closed"

    def test_a_cancelled_event_is_read_only(self, client, auth_headers, event_repository):
        """US4.6's rule, applied here as on every other route that changes an event."""
        seed_event(event_repository, EventStatus.CANCELLED)

        response = put_settings(client, auth_headers(COORDINATOR), {"open": True})

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "event-cancelled"

    def test_a_draft_is_not_found_by_a_coordinator(self, client, auth_headers, event_repository):
        seed_event(event_repository, EventStatus.DRAFT)
        assert put_settings(client, auth_headers(COORDINATOR), {"open": True}).status_code == 404

    @pytest.mark.parametrize("event_id", ["999", "abc"])
    def test_an_unknown_event_is_not_found(self, client, auth_headers, event_id):
        response = client.put(
            f"/events/{event_id}/registration",
            json={"open": True},
            headers=auth_headers(COORDINATOR),
        )
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

    def test_a_confirmed_event_never_opened_is_not_listed(
        self, client, auth_headers, event_repository
    ):
        seed_event(event_repository)
        assert open_events(client, auth_headers(ATTENDEE)).json() == []

    def test_the_venues_are_its_confirmed_bookings_once_each(
        self, client, auth_headers, event_repository, registration_repository, booking_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        booking_repository.bookings.extend(
            [
                booking(1, BookingStatus.CONFIRMED, "Great Hall"),
                booking(2, BookingStatus.CONFIRMED, "Seminar Room 4", venue_id=3),
                booking(3, BookingStatus.CONFIRMED, "Great Hall"),
                booking(4, BookingStatus.CANCELLED, "Bertha Room", venue_id=2),
                booking(5, BookingStatus.REJECTED, "Bertha Room", venue_id=2),
                booking(6, BookingStatus.CONFIRMED, "Bertha Room", event_id=OTHER_EVENT_ID),
            ]
        )

        shown = open_events(client, auth_headers(ATTENDEE)).json()[0]

        assert shown["venues"] == ["Great Hall", "Seminar Room 4"]

    def test_places_left_count_down_and_a_full_event_stays_listed(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 2)
        headers = auth_headers(ATTENDEE)

        assert open_events(client, headers).json()[0]["placesLeft"] == 2
        register(client, headers)
        assert open_events(client, headers).json()[0]["placesLeft"] == 1
        register(client, auth_headers(SECOND), name="Morgan Lee", email="morgan@example.com")
        assert open_events(client, headers).json()[0]["placesLeft"] == 0

    def test_soonest_first(self, client, auth_headers, event_repository, registration_repository):
        seed_event(event_repository, title="Later", starts_at="2099-12-01T09:00")
        seed_event(
            event_repository, event_id=OTHER_EVENT_ID, title="Sooner", starts_at="2099-10-01T09:00"
        )
        open_registration(registration_repository)
        open_registration(registration_repository, event_id=OTHER_EVENT_ID)

        titles = [item["title"] for item in open_events(client, auth_headers(ATTENDEE)).json()]

        assert titles == ["Sooner", "Later"]



    @pytest.mark.parametrize("event_id", ["999", "abc"])
    def test_an_unknown_event_is_not_open(self, client, auth_headers, event_id):
        response = client.get(f"/attendee/events/{event_id}", headers=auth_headers(ATTENDEE))
        assert response.status_code == 404
        assert response.json()["detail"] == {
            "code": "event_not_open",
            "message": "That event is not open for registration.",
        }

    @pytest.mark.parametrize(
        "role",
        [
            ORGANISER,
            COORDINATOR,
            "Event Coordinator Lead",
            "Venue Staff",
            "Safety Officer",
            "Technical Support",
        ],
    )
    def test_only_attendees_use_the_attendee_routes(
        self, client, auth_headers, event_repository, registration_repository, role
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        headers = auth_headers(role)

        assert open_events(client, headers).status_code == 403
        assert client.get(f"/attendee/events/{EVENT_ID}", headers=headers).status_code == 403
        assert register(client, headers).status_code == 403

    def test_signed_out_is_asked_to_sign_in(self, client):
        assert client.get("/attendee/events").status_code == 401

    @pytest.mark.parametrize(
        "path",
        [
            "/events",
            f"/events/{EVENT_ID}",
            f"/events/{EVENT_ID}/bookings",
            f"/events/{EVENT_ID}/equipment-requests",
            f"/events/{EVENT_ID}/registration",
            "/venues",
            # Not /notifications: since US4.6 an Attendee reads their own, which
            # say only that an event they registered for was cancelled.
        ],
    )
    def test_an_attendee_reaches_none_of_the_internal_routes(
        self, client, auth_headers, event_repository, registration_repository, path
    ):
        seed_event(event_repository)
        open_registration(registration_repository)

        assert client.get(path, headers=auth_headers(ATTENDEE)).status_code == 403


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

    def test_what_was_typed_is_trimmed(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)

        body = register(
            client, auth_headers(ATTENDEE), name="  Casey Tan ", email=" casey@example.com  "
        ).json()

        assert (body["name"], body["email"]) == ("Casey Tan", "casey@example.com")

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

    @pytest.mark.parametrize(
        "email", ["casey", "casey@", "@example.com", "casey@example", "casey tan@example.com"]
    )
    def test_an_email_that_cannot_be_one_is_refused(
        self, client, auth_headers, event_repository, registration_repository, email
    ):
        seed_event(event_repository)
        open_registration(registration_repository)

        response = register(client, auth_headers(ATTENDEE), email=email)

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == (
            "Give a valid email address, such as name@example.com."
        )

    def test_missing_fields_are_the_same_sentences(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)

        response = client.post(
            f"/attendee/events/{EVENT_ID}/registrations", json={}, headers=auth_headers(ATTENDEE)
        )

        assert response.status_code == 400
        assert response.json()["detail"]["message"] == "Give your name."

    def test_the_name_is_checked_before_the_email(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)

        response = register(client, auth_headers(ATTENDEE), name="", email="")

        assert response.json()["detail"]["message"] == "Give your name."


    @pytest.mark.parametrize("event_id", ["999", "abc"])
    def test_an_unknown_event_is_not_open(self, client, auth_headers, event_id):
        response = register(client, auth_headers(ATTENDEE), event_id=event_id)
        assert response.status_code == 404


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



    def test_already_registered_is_said_before_full(
        self, client, auth_headers, event_repository, registration_repository
    ):
        """A full event that already has your place: the useful answer is that it does."""
        seed_event(event_repository)
        open_registration(registration_repository, 1)
        headers = auth_headers(ATTENDEE)
        register(client, headers)

        assert register(client, headers).json()["detail"]["reason"] == "already-registered"


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

    def test_raising_the_capacity_takes_registrations_again(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 1)
        register(client, auth_headers(ATTENDEE))

        put_settings(client, auth_headers(COORDINATOR), {"open": True, "capacity": 2})
        response = register(
            client, auth_headers(SECOND), name="Morgan Lee", email="morgan@example.com"
        )

        assert response.status_code == 201, response.text

    def test_turning_registration_off_stops_new_ones_and_keeps_the_old(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        register(client, auth_headers(ATTENDEE))

        put_settings(client, auth_headers(COORDINATOR), {"open": False})
        response = register(
            client, auth_headers(SECOND), name="Morgan Lee", email="morgan@example.com"
        )

        assert response.status_code == 404
        assert len(registration_repository.registrations) == 1
        assert get_settings(client, auth_headers(COORDINATOR)).json()["registered"] == 1

    def test_closing_between_the_check_and_the_write_is_not_open(
        self, client, auth_headers, event_repository, registration_repository, monkeypatch
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        original = registration_repository.register

        def closed_meanwhile(event_id, **kwargs):
            registration_repository.settings[event_id] = (False, 30)
            return original(event_id, **kwargs)

        monkeypatch.setattr(registration_repository, "register", closed_meanwhile)

        assert register(client, auth_headers(ATTENDEE)).status_code == 404

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

    def test_one_place_reads_in_the_singular(
        self, client, auth_headers, event_repository, registration_repository,
        notification_repository,
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 1)

        register(client, auth_headers(ATTENDEE))

        assert {notice.message for notice in full_notices(notification_repository)} == {
            '"Open House" is full: its one place is taken.'
        }

    def test_a_refused_registration_says_nothing_new(
        self, client, auth_headers, event_repository, registration_repository,
        notification_repository,
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 1)
        register(client, auth_headers(ATTENDEE))

        register(client, auth_headers(SECOND), name="Morgan Lee", email="morgan@example.com")

        assert len(full_notices(notification_repository)) == 2

    def test_filling_again_after_more_places_tells_them_again(
        self, client, auth_headers, event_repository, registration_repository,
        notification_repository,
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 1)
        register(client, auth_headers(ATTENDEE))
        put_settings(client, auth_headers(COORDINATOR), {"open": True, "capacity": 2})

        register(client, auth_headers(SECOND), name="Morgan Lee", email="morgan@example.com")

        assert len(full_notices(notification_repository)) == 4

    def test_with_no_coordinator_the_organiser_is_still_told(
        self, event_repository, registration_repository, notification_repository
    ):
        seed_event(event_repository, coordinator_id=None)
        open_registration(registration_repository, 1)

        _tell_full(EVENT_ID)

        assert [notice.user_id for notice in full_notices(notification_repository)] == [
            ORGANISER_ID
        ]

    def test_both_read_it_on_their_notifications_page(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 1)
        register(client, auth_headers(ATTENDEE))

        for role in (ORGANISER, COORDINATOR):
            listed = client.get("/notifications", headers=auth_headers(role)).json()
            assert [(item["kind"], item["eventTitle"], item["status"]) for item in listed] == [
                ("event-full", "Open House", None)
            ]

    def test_a_notice_that_cannot_be_written_never_undoes_the_registration(
        self, client, auth_headers, event_repository, registration_repository,
        notification_repository, monkeypatch,
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 1)

        def broken(**_kwargs):
            raise RuntimeError("notifications table unavailable")

        monkeypatch.setattr(notification_repository, "create_notice", broken)

        response = register(client, auth_headers(ATTENDEE))

        assert response.status_code == 201, response.text
        assert len(registration_repository.registrations) == 1

    def test_a_failed_read_for_the_notice_does_not_undo_it_either(
        self, client, auth_headers, event_repository, registration_repository,
        notification_repository, monkeypatch,
    ):
        """The capacity is read again only to word the notice."""
        seed_event(event_repository)
        open_registration(registration_repository, 1)

        def unavailable(_event_id):
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(registration_repository, "settings_for", unavailable)

        assert register(client, auth_headers(ATTENDEE)).status_code == 201
        assert len(registration_repository.registrations) == 1
        assert full_notices(notification_repository) == []


class TestTheAttendeeRole:
    def test_an_attendee_signs_in_and_lands_on_the_open_events(self, sign_in):
        session = sign_in(ATTENDEE)

        assert session["role"] == "Attendee"
        assert session["home"] == "/attend"
        # US4.6 added notifications:read, for an event they registered for being cancelled.
        assert sorted(session["permissions"]) == ["notifications:read", "registrations:create"]

    def test_each_permission_belongs_to_one_role(self):
        assert roles_with(Permission.REGISTRATIONS_CREATE) == [Role.ATTENDEE]
        assert roles_with(Permission.REGISTRATION_MANAGE) == [Role.COORDINATOR]


class TestEndToEnd:
    def test_opened_in_planning_listed_once_confirmed_then_filled(
        self, client, auth_headers, event_repository, notification_repository
    ):
        seed_event(event_repository, EventStatus.PLANNING)
        coordinator = auth_headers(COORDINATOR)
        attendee = auth_headers(ATTENDEE)

        assert put_settings(client, coordinator, {"open": True, "capacity": 1}).status_code == 200
        assert open_events(client, attendee).json() == []

        confirmed = replace(event_repository.get_event(EVENT_ID), status=EventStatus.CONFIRMED)
        event_repository.events = [confirmed]

        assert [item["id"] for item in open_events(client, attendee).json()] == [str(EVENT_ID)]
        assert register(client, attendee).status_code == 201
        listed = open_events(client, attendee).json()[0]
        assert (listed["placesLeft"], listed["registered"]) == (0, True)
        assert len(full_notices(notification_repository)) == 2

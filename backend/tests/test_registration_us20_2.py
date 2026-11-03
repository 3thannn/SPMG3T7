"""US20.2: an Attendee sees their registrations and withdraws.

Acceptance criteria, and the tests that hold each one:

* An Attendee sees their registrations with status (Registered or Withdrawn)
  and the event's current date, time and venue -> `TestMyRegistrations`.
* An Attendee can withdraw before the event starts; the places left go up by
  one -> `TestWithdrawing`, `TestTheRule`.
* A withdrawn Attendee can register again if places are still available ->
  `TestRegisteringAgain`.

The database half is test_registration_db.py (`TestWithdrawingInTheDatabase`,
opt-in) and TEST_US20_2_WITHDRAW.sql.
"""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from app import registration_store
from app.booking_store import BookingStatus
from app.registration_store import (
    RegistrationStatus,
)
from tests.test_registration_us20_1 import (
    ATTENDEE,
    COORDINATOR,
    EVENT_ID,
    SECOND,
    booking,
    get_settings,
    open_events,
    open_registration,
    register,
    seed_event,
)

PAST = "2000-01-01T09:00"


def mine(client, headers):
    return client.get("/attendee/registrations", headers=headers)


def withdraw(client, headers, registration_id):
    return client.post(f"/attendee/registrations/{registration_id}/withdraw", headers=headers)


def registered(client, headers, **kwargs) -> str:
    response = register(client, headers, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def as_morgan(client, auth_headers, **kwargs):
    return register(
        client, auth_headers(SECOND), name="Morgan Lee", email="morgan@example.com", **kwargs
    )


def move(event_repository, event_id=EVENT_ID, **changes):
    """Change an event after the fact, as a Coordinator or Lead would."""
    event_repository.events = [
        replace(event, **changes) if event.id == event_id else event
        for event in event_repository.events
    ]




class TestMyRegistrations:
    """AC1: their registrations, with status and the event as it stands now."""

    def test_an_attendee_sees_their_registration(
        self, client, auth_headers, event_repository, registration_repository, booking_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 30)
        booking_repository.bookings.append(booking(1, BookingStatus.CONFIRMED, "Great Hall"))
        headers = auth_headers(ATTENDEE)
        registration_id = registered(client, headers)

        response = mine(client, headers)

        assert response.status_code == 200, response.text
        (item,) = response.json()
        assert item["registeredAt"]
        assert {key: value for key, value in item.items() if key != "registeredAt"} == {
            "id": registration_id,
            "eventId": str(EVENT_ID),
            "title": "Open House",
            "startsAt": "2099-11-02T09:00",
            "endsAt": "2099-11-02T17:00",
            "venues": ["Great Hall"],
            "status": "Registered",
            "name": "Casey Tan",
            "email": "casey@example.com",
            "withdrawnAt": "",
            "canWithdraw": True,
            "canRegisterAgain": False,
            "placesLeft": 29,
        }


    def test_a_withdrawn_registration_is_listed_as_withdrawn(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        headers = auth_headers(ATTENDEE)
        withdraw(client, headers, registered(client, headers))

        (item,) = mine(client, headers).json()

        assert item["status"] == "Withdrawn"
        assert item["withdrawnAt"]
        assert item["canWithdraw"] is False










class TestWithdrawing:
    """AC2: before the event starts, and the place goes back."""


    def test_the_places_left_go_up_by_one(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 2)
        headers = auth_headers(ATTENDEE)
        registration_id = registered(client, headers)
        as_morgan(client, auth_headers)
        assert open_events(client, headers).json()[0]["placesLeft"] == 0

        withdraw(client, headers, registration_id)

        assert open_events(client, headers).json()[0]["placesLeft"] == 1
        settings = get_settings(client, auth_headers(COORDINATOR)).json()
        assert (settings["registered"], settings["placesLeft"]) == (1, 1)



    def test_once_the_event_has_started_it_is_too_late(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        headers = auth_headers(ATTENDEE)
        registration_id = registered(client, headers)
        move(event_repository, starts_at=PAST)

        response = withdraw(client, headers, registration_id)

        assert response.status_code == 409
        assert response.json()["detail"] == {
            "code": "rule_refused",
            "message": "This event has already started, so you can no longer withdraw.",
            "reason": "event-started",
        }
        assert registration_repository.registrations[0].status is RegistrationStatus.REGISTERED
        assert mine(client, headers).json()[0]["canWithdraw"] is False

    @pytest.mark.parametrize(("minutes_before", "allowed"), [(1, True), (0, False)])
    def test_up_to_the_minute_before_it_starts(
        self, client, auth_headers, event_repository, registration_repository, monkeypatch,
        minutes_before, allowed,
    ):
        seed_event(event_repository, starts_at="2099-11-02T09:00")
        open_registration(registration_repository)
        headers = auth_headers(ATTENDEE)
        registration_id = registered(client, headers)
        now = datetime(2099, 11, 2, 9, 0) - timedelta(minutes=minutes_before)
        monkeypatch.setattr(registration_store, "local_now", lambda: now)

        response = withdraw(client, headers, registration_id)

        assert (response.status_code == 200) is allowed







class TestRegisteringAgain:
    """AC3: a withdrawn Attendee registers again while there are places."""

    def test_a_withdrawn_attendee_registers_again(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 5)
        headers = auth_headers(ATTENDEE)
        withdraw(client, headers, registered(client, headers))

        response = register(client, headers)

        assert response.status_code == 201, response.text
        assert [item.status for item in registration_repository.registrations] == [
            RegistrationStatus.WITHDRAWN,
            RegistrationStatus.REGISTERED,
        ]
        assert open_events(client, headers).json()[0]["registered"] is True
        assert get_settings(client, auth_headers(COORDINATOR)).json()["registered"] == 1

    def test_not_once_the_places_have_gone(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 1)
        headers = auth_headers(ATTENDEE)
        withdraw(client, headers, registered(client, headers))
        assert as_morgan(client, auth_headers).status_code == 201

        response = register(client, headers)

        assert response.status_code == 409
        assert response.json()["detail"]["message"] == "Event is full."
        (item,) = mine(client, headers).json()
        assert (item["status"], item["canRegisterAgain"], item["placesLeft"]) == (
            "Withdrawn",
            False,
            0,
        )






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
from app.event_status import EventStatus
from app.registration_store import (
    RegisteredEvent,
    Registration,
    RegistrationStatus,
    WithdrawOutcome,
    withdrawal_refusal,
)
from tests.conftest import ATTENDEE_ID, SECOND_ATTENDEE_ID
from tests.test_registration_us20_1 import (
    ATTENDEE,
    COORDINATOR,
    EVENT_ID,
    OTHER_EVENT_ID,
    SECOND,
    booking,
    full_notices,
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


class TestTheRule:
    NOW = datetime(2026, 10, 23, 12, 0)

    def registration(self, status=RegistrationStatus.REGISTERED):
        return Registration(
            id=1,
            event_id=EVENT_ID,
            attendee_id=ATTENDEE_ID,
            name="Casey",
            email="casey@example.com",
            status=status,
            created_at="2026-10-01T09:00:00",
        )

    def event(self, starts_at="2026-10-23T12:01", status=EventStatus.CONFIRMED):
        return RegisteredEvent(title="Open House", starts_at=starts_at, ends_at="", status=status)

    def test_a_registration_before_its_confirmed_event_starts_may_be_withdrawn(self):
        assert withdrawal_refusal(self.registration(), self.event(), self.NOW) is None

    def test_not_once_withdrawn(self):
        refusal = withdrawal_refusal(
            self.registration(RegistrationStatus.WITHDRAWN), self.event(), self.NOW
        )
        assert refusal is WithdrawOutcome.ALREADY_WITHDRAWN

    @pytest.mark.parametrize("starts_at", ["2026-10-23T12:00", "2026-10-23T11:59", PAST])
    def test_not_at_or_after_the_start(self, starts_at):
        refusal = withdrawal_refusal(self.registration(), self.event(starts_at), self.NOW)
        assert refusal is WithdrawOutcome.STARTED

    @pytest.mark.parametrize(
        "status", [EventStatus.COMPLETED, EventStatus.CANCELLED, EventStatus.PLANNING]
    )
    def test_not_once_the_event_is_no_longer_confirmed(self, status):
        refusal = withdrawal_refusal(
            self.registration(), self.event(status=status), self.NOW
        )
        assert refusal is WithdrawOutcome.CLOSED

    def test_not_for_an_event_that_is_gone(self):
        assert withdrawal_refusal(self.registration(), None, self.NOW) is WithdrawOutcome.CLOSED

    def test_an_event_with_no_start_recorded_has_not_started(self):
        assert withdrawal_refusal(self.registration(), self.event(""), self.NOW) is None


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

    def test_the_event_details_are_the_current_ones(
        self, client, auth_headers, event_repository, registration_repository, booking_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        headers = auth_headers(ATTENDEE)
        registered(client, headers)

        move(event_repository, title="Open House (moved)", starts_at="2099-12-05T10:00")
        booking_repository.bookings.append(booking(1, BookingStatus.CONFIRMED, "Bertha Room"))

        (item,) = mine(client, headers).json()
        assert (item["title"], item["startsAt"], item["venues"]) == (
            "Open House (moved)",
            "2099-12-05T10:00",
            ["Bertha Room"],
        )

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

    def test_only_your_own(self, client, auth_headers, event_repository, registration_repository):
        seed_event(event_repository)
        open_registration(registration_repository)
        registered(client, auth_headers(ATTENDEE))
        as_morgan(client, auth_headers)

        names = [item["name"] for item in mine(client, auth_headers(ATTENDEE)).json()]

        assert names == ["Casey Tan"]

    def test_soonest_event_first(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository, title="Later", starts_at="2099-12-01T09:00")
        seed_event(
            event_repository, event_id=OTHER_EVENT_ID, title="Sooner", starts_at="2099-10-01T09:00"
        )
        open_registration(registration_repository)
        open_registration(registration_repository, event_id=OTHER_EVENT_ID)
        headers = auth_headers(ATTENDEE)
        registered(client, headers)
        registered(client, headers, event_id=OTHER_EVENT_ID)

        assert [item["title"] for item in mine(client, headers).json()] == ["Sooner", "Later"]

    def test_one_entry_per_event_where_they_stand_now(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        headers = auth_headers(ATTENDEE)
        first = registered(client, headers)
        withdraw(client, headers, first)
        again = registered(client, headers)

        listed = mine(client, headers).json()

        assert [(item["id"], item["status"]) for item in listed] == [(again, "Registered")]

    def test_an_event_no_longer_taking_registrations_still_shows(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        headers = auth_headers(ATTENDEE)
        registered(client, headers)
        registration_repository.settings[EVENT_ID] = (False, 30)

        (item,) = mine(client, headers).json()

        assert (item["status"], item["placesLeft"], item["canWithdraw"]) == (
            "Registered",
            None,
            True,
        )

    def test_nothing_of_the_planning_is_shown(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        headers = auth_headers(ATTENDEE)
        registered(client, headers)

        (item,) = mine(client, headers).json()

        assert "Internal" not in str(item)
        assert "Dylan" not in str(item) and "Priya" not in str(item)

    def test_none_is_an_empty_list(self, client, auth_headers):
        assert mine(client, auth_headers(ATTENDEE)).json() == []

    @pytest.mark.parametrize(
        "role", ["Event Organiser", COORDINATOR, "Event Coordinator Lead", "Venue Staff"]
    )
    def test_only_attendees_have_registrations_to_see(self, client, auth_headers, role):
        assert mine(client, auth_headers(role)).status_code == 403
        assert withdraw(client, auth_headers(role), "1").status_code == 403

    def test_signed_out_is_asked_to_sign_in(self, client):
        assert client.get("/attendee/registrations").status_code == 401
        assert client.post("/attendee/registrations/1/withdraw").status_code == 401


class TestWithdrawing:
    """AC2: before the event starts, and the place goes back."""

    def test_an_attendee_withdraws_before_the_event_starts(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 30)
        headers = auth_headers(ATTENDEE)
        registration_id = registered(client, headers)

        response = withdraw(client, headers, registration_id)

        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["id"], body["status"], body["canWithdraw"]) == (
            registration_id,
            "Withdrawn",
            False,
        )
        assert body["withdrawnAt"]
        assert (body["canRegisterAgain"], body["placesLeft"]) == (True, 30)

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

    def test_the_freed_place_can_be_taken_by_someone_else(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 1)
        headers = auth_headers(ATTENDEE)
        registration_id = registered(client, headers)
        assert as_morgan(client, auth_headers).status_code == 409

        withdraw(client, headers, registration_id)

        assert as_morgan(client, auth_headers).status_code == 201

    def test_the_registration_is_kept_as_history(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        headers = auth_headers(ATTENDEE)
        withdraw(client, headers, registered(client, headers))

        (stored,) = registration_repository.registrations
        assert stored.status is RegistrationStatus.WITHDRAWN
        assert stored.withdrawn_at

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

    def test_withdrawing_twice_is_refused_with_the_reason(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        headers = auth_headers(ATTENDEE)
        registration_id = registered(client, headers)
        withdraw(client, headers, registration_id)

        again = withdraw(client, headers, registration_id)

        assert again.status_code == 409
        assert again.json()["detail"]["reason"] == "already-withdrawn"
        assert again.json()["detail"]["message"] == "You have already withdrawn from this event."

    @pytest.mark.parametrize("status", [EventStatus.COMPLETED, EventStatus.CANCELLED])
    def test_an_event_no_longer_going_ahead_is_refused(
        self, client, auth_headers, event_repository, registration_repository, status
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        headers = auth_headers(ATTENDEE)
        registration_id = registered(client, headers)
        move(event_repository, status=status)

        response = withdraw(client, headers, registration_id)

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "event-closed"

    def test_registration_turned_off_still_lets_you_withdraw(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        headers = auth_headers(ATTENDEE)
        registration_id = registered(client, headers)
        registration_repository.settings[EVENT_ID] = (False, 30)

        response = withdraw(client, headers, registration_id)

        assert response.status_code == 200, response.text
        assert (response.json()["canRegisterAgain"], response.json()["placesLeft"]) == (
            False,
            None,
        )

    def test_someone_elses_registration_is_not_found(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        registration_id = registered(client, auth_headers(ATTENDEE))

        response = withdraw(client, auth_headers(SECOND), registration_id)

        assert response.status_code == 404
        assert response.json()["detail"] == {
            "code": "registration_not_found",
            "message": "That registration no longer exists.",
        }
        assert registration_repository.registrations[0].status is RegistrationStatus.REGISTERED

    @pytest.mark.parametrize("registration_id", ["999", "abc"])
    def test_an_unknown_registration_is_not_found(self, client, auth_headers, registration_id):
        assert withdraw(client, auth_headers(ATTENDEE), registration_id).status_code == 404


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

    def test_not_once_registration_is_turned_off(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        headers = auth_headers(ATTENDEE)
        withdraw(client, headers, registered(client, headers))
        registration_repository.settings[EVENT_ID] = (False, 30)

        assert mine(client, headers).json()[0]["canRegisterAgain"] is False
        assert register(client, headers).status_code == 404

    def test_taking_the_last_place_again_tells_them_it_is_full(
        self, client, auth_headers, event_repository, registration_repository,
        notification_repository,
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 1)
        headers = auth_headers(ATTENDEE)
        withdraw(client, headers, registered(client, headers))
        assert len(full_notices(notification_repository)) == 2

        register(client, headers)

        assert len(full_notices(notification_repository)) == 4

    def test_the_second_attendee_is_unaffected(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 5)
        headers = auth_headers(ATTENDEE)
        withdraw(client, headers, registered(client, headers))
        as_morgan(client, auth_headers)

        active = registration_repository.registered_event_ids(SECOND_ATTENDEE_ID)

        assert active == frozenset({EVENT_ID})


class TestEndToEnd:
    def test_register_withdraw_and_register_again(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 1)
        casey = auth_headers(ATTENDEE)

        first = registered(client, casey)
        assert mine(client, casey).json()[0]["canWithdraw"] is True
        assert withdraw(client, casey, first).status_code == 200
        assert open_events(client, casey).json()[0]["placesLeft"] == 1
        again = registered(client, casey)

        listed = mine(client, casey).json()
        assert [(item["id"], item["status"]) for item in listed] == [(again, "Registered")]
        assert open_events(client, casey).json()[0]["placesLeft"] == 0

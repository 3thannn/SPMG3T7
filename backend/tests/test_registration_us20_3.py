"""US20.3: the Organiser and the Coordinator see who registered.

Acceptance criteria, and the tests that hold each one:

* The owning Organiser and the assigned Coordinator can see the registration
  list: name, email, registration time, status, and the registered count
  against the capacity -> `TestWhoMaySeeTheList` (the two who may),
  `TestWhatTheListShows`.
* Other Organisers and non-assigned Coordinators are blocked (US3.1 / US8.6
  rules). Attendees can't see other Attendees' registrations ->
  `TestWhoMaySeeTheList`, `TestAttendeesSeeOnlyTheirOwn`.
"""

import pytest

from app.permissions import Role
from app.users import User
from tests.conftest import COORDINATOR_ID, PASSWORD
from tests.test_registration_us20_1 import (
    ATTENDEE,
    COORDINATOR,
    EVENT_ID,
    open_events,
    open_registration,
    seed_event,
)
from tests.test_registration_us20_2 import as_morgan, registered, withdraw

ORGANISER = "Event Organiser"
OTHER_ORGANISER_ID = 30
OTHER_COORDINATOR_ID = 31


def people(client, headers, *, event_id=EVENT_ID):
    return client.get(f"/events/{event_id}/registrations", headers=headers)


def another(user_store, client, user_id: int, role: Role) -> dict[str, str]:
    """A second account of a role, signed in, for the "not yours" cases."""
    email = f"user{user_id}@spmg3t7.edu"
    user_store.users.append(User(id=user_id, email=email, name=f"User {user_id}", role=role))
    user_store.passwords[email] = PASSWORD
    signed_in = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert signed_in.status_code == 200, signed_in.text
    return {"Authorization": f"Bearer {signed_in.json()['token']}"}


class TestWhoMaySeeTheList:
    @pytest.mark.parametrize("role", [ORGANISER, COORDINATOR])
    def test_the_owning_organiser_and_the_assigned_coordinator_see_it(
        self, client, auth_headers, event_repository, registration_repository, role
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        registered(client, auth_headers(ATTENDEE))

        response = people(client, auth_headers(role))

        assert response.status_code == 200, response.text
        assert [item["name"] for item in response.json()["registrations"]] == ["Casey Tan"]

    def test_another_organiser_is_told_it_does_not_exist(
        self, client, auth_headers, event_repository, registration_repository, user_store
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        registered(client, auth_headers(ATTENDEE))

        response = people(client, another(user_store, client, OTHER_ORGANISER_ID, Role.ORGANISER))

        assert response.status_code == 404
        assert "Casey" not in response.text

    def test_a_coordinator_not_assigned_is_told_it_does_not_exist(
        self, client, auth_headers, event_repository, registration_repository, user_store
    ):
        seed_event(event_repository, coordinator_id=COORDINATOR_ID)
        open_registration(registration_repository)
        registered(client, auth_headers(ATTENDEE))

        response = people(
            client, another(user_store, client, OTHER_COORDINATOR_ID, Role.COORDINATOR)
        )

        assert response.status_code == 404
        assert "Casey" not in response.text








class TestWhatTheListShows:
    """AC1: name, email, registration time, status, and the count against capacity."""

    def test_each_person_with_the_count_against_the_capacity(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 50)
        casey = registered(client, auth_headers(ATTENDEE))
        morgan = as_morgan(client, auth_headers).json()["id"]

        body = people(client, auth_headers(COORDINATOR)).json()

        counts = ("eventId", "open", "capacity", "registered", "placesLeft")
        assert {key: body[key] for key in counts} == {
            "eventId": str(EVENT_ID),
            "open": True,
            "capacity": 50,
            "registered": 2,
            "placesLeft": 48,
        }
        assert [
            {key: item[key] for key in ("id", "name", "email", "status", "withdrawnAt")}
            for item in body["registrations"]
        ] == [
            {
                "id": casey,
                "name": "Casey Tan",
                "email": "casey@example.com",
                "status": "Registered",
                "withdrawnAt": "",
            },
            {
                "id": morgan,
                "name": "Morgan Lee",
                "email": "morgan@example.com",
                "status": "Registered",
                "withdrawnAt": "",
            },
        ]
        assert all(item["registeredAt"] for item in body["registrations"])


    def test_a_withdrawn_registration_is_listed_and_not_counted(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository, 50)
        headers = auth_headers(ATTENDEE)
        withdraw(client, headers, registered(client, headers))

        body = people(client, auth_headers(ORGANISER)).json()

        (item,) = body["registrations"]
        assert (item["status"], bool(item["withdrawnAt"])) == ("Withdrawn", True)
        assert (body["registered"], body["placesLeft"]) == (0, 50)








class TestAttendeesSeeOnlyTheirOwn:
    """AC2: an Attendee never sees anyone else's registration."""

    def test_an_attendee_cannot_open_an_events_list(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        as_morgan(client, auth_headers)

        response = people(client, auth_headers(ATTENDEE))

        assert response.status_code == 403
        assert "Morgan" not in response.text


    def test_the_open_events_carry_no_one_elses_details(
        self, client, auth_headers, event_repository, registration_repository
    ):
        seed_event(event_repository)
        open_registration(registration_repository)
        as_morgan(client, auth_headers)

        shown = open_events(client, auth_headers(ATTENDEE)).text

        assert "Morgan" not in shown and "morgan@example.com" not in shown



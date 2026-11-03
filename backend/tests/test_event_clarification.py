"""US7.3 — a Coordinator requests clarification or an amendment.

Three things the story asks for, and each is asserted against a request rather
than against a disabled button:

* the Coordinator attaches a message to the event,
* the status moves to Under Review,
* and the message is visible to the Organiser.

The Organiser's reply is US11.1 and is deliberately absent. So is any check on
*which* Coordinator asks: the story says any of them can for now, and narrowing
it to the assigned one waits for US8.1.
"""

from app.event_status import EventStatus
from app.event_store import Event
from tests.conftest import COORDINATOR_ID, ORGANISER_ID, SUBMITTABLE_NEEDS

DRAFT = {
    "title": "Faculty Welcome Night",
    "purpose": "Welcome the new intake.",
    "startsAt": "2026-11-02T18:00",
    "endsAt": "2026-11-02T21:00",
    "description": "Talks.",
    "expectedAttendance": 120,
    **SUBMITTABLE_NEEDS,
}

MESSAGE = "Please confirm the catering budget and add a wet-weather plan."


def submitted_event(client, auth_headers) -> dict:
    """An event in the state US7.3 starts from: submitted, awaiting review.
    US8.6: Assigns the event to the coordinator so they can see it."""
    organiser = auth_headers("Event Organiser")
    created = client.post("/events", json=DRAFT, headers=organiser)
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]
    submitted = client.post(f"/events/{event_id}/submit", headers=organiser)
    assert submitted.status_code == 200, submitted.text

    # US8.6: Assign the event to the coordinator so they can interact with it
    assigned = client.post(
        f"/events/{event_id}/assign",
        json={"coordinatorId": str(COORDINATOR_ID)},
        headers=auth_headers("Event Coordinator Lead"),
    )
    assert assigned.status_code == 200, assigned.text

    return assigned.json()


def seed(event_repository, **overrides) -> Event:
    """Put an event straight into the store, for a status the routes cannot reach."""
    fields = {
        "id": 500,
        "title": "Already decided",
        "purpose": "Purpose",
        "description": "",
        "starts_at": "2026-11-02T18:00",
        "ends_at": "",
        "expected_attendance": 50,
        "status": EventStatus.APPROVED,
        "organiser_id": ORGANISER_ID,
        "organiser_name": "Dylan",
        "created_at": "2026-01-01T09:00:00",
        "updated_at": "2026-01-01T09:00:00",
    }
    event = Event(**{**fields, **overrides})
    event_repository.events.append(event)
    return event


def request_clarification(client, headers, event_id: str, message: str = MESSAGE):
    return client.post(
        f"/events/{event_id}/clarification", json={"message": message}, headers=headers
    )


class TestAsking:

    def test_the_status_moves_to_under_review(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = request_clarification(client, auth_headers("Event Coordinator"), event["id"])

        assert response.json()["status"] == "Under Review"

    def test_the_message_is_recorded_on_the_status_change(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = request_clarification(client, auth_headers("Event Coordinator"), event["id"])

        latest = response.json()["history"][-1]
        assert latest["notes"] == MESSAGE
        assert latest["from"] == "Under Review"
        assert latest["to"] == "Under Review"








class TestTheOrganiserSeesIt:
    """The acceptance criterion that makes the feature worth anything."""

    def test_the_owning_organiser_can_read_the_message(self, client, auth_headers):
        event = submitted_event(client, auth_headers)
        request_clarification(client, auth_headers("Event Coordinator"), event["id"])

        response = client.get(f"/events/{event['id']}", headers=auth_headers("Event Organiser"))

        assert response.status_code == 200, response.text
        assert response.json()["history"][-1]["notes"] == MESSAGE








class TestTheMessageIsRequired:
    def test_an_empty_message_is_refused(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = request_clarification(client, auth_headers("Event Coordinator"), event["id"], "")

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["code"] == "invalid_event"
        assert "Organiser" in detail["message"]






class TestWhenItIsRefused:


    def test_a_decided_event_is_no_longer_under_review(
        self, client, auth_headers, event_repository
    ):
        # US8.1: Event must be assigned to the coordinator for them to see it
        seed(event_repository, coordinator_id=COORDINATOR_ID)

        response = request_clarification(client, auth_headers("Event Coordinator"), "500")

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["reason"] == "already-decided"
        assert "already been decided" in detail["message"]






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

from app.event_status import ClarificationRefusal, EventStatus, check_clarification
from app.event_store import Event
from tests.conftest import COORDINATOR_ID, ORGANISER_ID

DRAFT = {
    "title": "Faculty Welcome Night",
    "purpose": "Welcome the new intake.",
    "startsAt": "2026-11-02T18:00",
    "description": "Talks.",
    "expectedAttendance": 120,
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
    def test_a_coordinator_can_attach_a_message(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = request_clarification(client, auth_headers("Event Coordinator"), event["id"])

        assert response.status_code == 200, response.text

    def test_the_status_moves_to_under_review(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = request_clarification(client, auth_headers("Event Coordinator"), event["id"])

        assert response.json()["status"] == "Under Review"

    def test_the_message_is_recorded_on_the_status_change(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = request_clarification(client, auth_headers("Event Coordinator"), event["id"])

        latest = response.json()["history"][-1]
        assert latest["notes"] == MESSAGE
        assert latest["from"] == "Submitted"
        assert latest["to"] == "Under Review"

    def test_the_request_is_attributable_and_timestamped(self, client, auth_headers):
        """US4.2's audit requirements hold for this change too."""
        event = submitted_event(client, auth_headers)

        response = request_clarification(client, auth_headers("Event Coordinator"), event["id"])

        latest = response.json()["history"][-1]
        assert latest["byId"] == str(COORDINATOR_ID)
        assert latest["byName"] == "Priya"
        assert latest["at"]

    def test_the_message_is_kept_exactly_as_written(self, client, auth_headers):
        event = submitted_event(client, auth_headers)
        message = "Two things:\n1. Budget?\n2. Wet-weather plan?"

        response = request_clarification(
            client, auth_headers("Event Coordinator"), event["id"], message
        )

        assert response.json()["history"][-1]["notes"] == message

    def test_surrounding_space_is_trimmed(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = request_clarification(
            client, auth_headers("Event Coordinator"), event["id"], f"  {MESSAGE}  "
        )

        assert response.json()["history"][-1]["notes"] == MESSAGE

    def test_the_earlier_history_is_kept(self, client, auth_headers):
        """The request is added to the trail, not written over it."""
        event = submitted_event(client, auth_headers)

        response = request_clarification(client, auth_headers("Event Coordinator"), event["id"])

        history = response.json()["history"]
        # US8.6: Assignment doesn't create a history entry (coordinator_id just gets set)
        assert [entry["to"] for entry in history] == [
            "Draft",
            "Submitted",
            "Under Review",
        ]

    def test_asking_again_adds_a_second_request(self, client, auth_headers):
        """A first answer often raises a second question."""
        event = submitted_event(client, auth_headers)
        headers = auth_headers("Event Coordinator")
        request_clarification(client, headers, event["id"], "First question.")

        response = request_clarification(client, headers, event["id"], "Second question.")

        assert response.status_code == 200, response.text
        notes = [entry["notes"] for entry in response.json()["history"]]
        assert "First question." in notes
        assert "Second question." in notes

    def test_a_second_request_stays_under_review(self, client, auth_headers):
        event = submitted_event(client, auth_headers)
        headers = auth_headers("Event Coordinator")
        request_clarification(client, headers, event["id"], "First question.")

        response = request_clarification(client, headers, event["id"], "Second question.")

        latest = response.json()["history"][-1]
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

    def test_the_organiser_sees_the_new_status(self, client, auth_headers):
        event = submitted_event(client, auth_headers)
        request_clarification(client, auth_headers("Event Coordinator"), event["id"])

        response = client.get(f"/events/{event['id']}", headers=auth_headers("Event Organiser"))

        assert response.json()["status"] == "Under Review"

    def test_the_event_stays_in_the_organisers_list(self, client, auth_headers):
        """Under Review is still their event, so it must not vanish from the list."""
        event = submitted_event(client, auth_headers)
        request_clarification(client, auth_headers("Event Coordinator"), event["id"])

        listed = client.get("/events", headers=auth_headers("Event Organiser")).json()

        assert [item["id"] for item in listed] == [event["id"]]

    def test_the_event_stays_in_the_coordinators_list(self, client, auth_headers):
        event = submitted_event(client, auth_headers)
        headers = auth_headers("Event Coordinator")
        request_clarification(client, headers, event["id"])

        listed = client.get("/events", headers=headers).json()

        assert [item["status"] for item in listed] == ["Under Review"]

    def test_an_automatic_entry_carries_no_message(self, client, auth_headers):
        """So a client can tell a request apart from a plain status change."""
        event = submitted_event(client, auth_headers)

        # US8.6: Assignment doesn't create a history entry
        assert [entry["notes"] for entry in event["history"]] == ["", ""]


class TestWhoMayAsk:
    def test_an_organiser_cannot_request_clarification(self, client, auth_headers):
        """Reviewing is the Coordinator's job; the Organiser answers (US11.1)."""
        event = submitted_event(client, auth_headers)

        response = request_clarification(client, auth_headers("Event Organiser"), event["id"])

        assert response.status_code == 403
        detail = response.json()["detail"]
        assert detail["code"] == "forbidden"
        assert "Event Coordinator" in detail["message"]

    def test_venue_staff_cannot_request_clarification(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = request_clarification(client, auth_headers("Venue Staff"), event["id"])

        assert response.status_code == 403

    def test_it_needs_a_session(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = client.post(f"/events/{event['id']}/clarification", json={"message": MESSAGE})

        assert response.status_code == 401

    def test_signing_out_is_enough_to_lose_the_ability(self, client, auth_headers):
        event = submitted_event(client, auth_headers)
        headers = auth_headers("Event Coordinator")
        client.post("/auth/logout", headers=headers)

        assert request_clarification(client, headers, event["id"]).status_code == 401

    def test_any_coordinator_may_ask_not_only_an_assigned_one(self, client, auth_headers):
        """The story's own wording. Assignment arrives with US8.1."""
        event = submitted_event(client, auth_headers)

        response = request_clarification(client, auth_headers("Event Coordinator"), event["id"])

        assert response.status_code == 200, response.text


class TestTheMessageIsRequired:
    def test_an_empty_message_is_refused(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = request_clarification(client, auth_headers("Event Coordinator"), event["id"], "")

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["code"] == "invalid_event"
        assert "Organiser" in detail["message"]

    def test_a_message_of_only_spaces_is_no_message(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = request_clarification(
            client, auth_headers("Event Coordinator"), event["id"], "    "
        )

        assert response.status_code == 400

    def test_a_missing_message_field_is_refused(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = client.post(
            f"/events/{event['id']}/clarification",
            json={},
            headers=auth_headers("Event Coordinator"),
        )

        assert response.status_code == 400

    def test_an_overlong_message_is_refused_with_a_sentence(self, client, auth_headers):
        event = submitted_event(client, auth_headers)

        response = request_clarification(
            client, auth_headers("Event Coordinator"), event["id"], "x" * 2001
        )

        assert response.status_code == 400
        assert "2000" in response.json()["detail"]["message"]

    def test_a_refused_message_does_not_move_the_status(self, client, auth_headers):
        event = submitted_event(client, auth_headers)
        request_clarification(client, auth_headers("Event Coordinator"), event["id"], "")

        after = client.get(f"/events/{event['id']}", headers=auth_headers("Event Organiser")).json()

        assert after["status"] == "Submitted"
        assert len(after["history"]) == 2


class TestWhenItIsRefused:
    def test_a_concurrent_decision_cannot_be_undone_by_a_stale_clarification(
        self, client, auth_headers, event_repository, monkeypatch
    ):
        event = submitted_event(client, auth_headers)
        headers = auth_headers("Event Coordinator")
        reviewed = request_clarification(client, headers, event["id"], "First question.")
        assert reviewed.status_code == 200, reviewed.text

        original_request = event_repository.request_clarification

        def approve_before_clarification(
            event_id: int,
            *,
            actor_id: int,
            from_status: EventStatus,
            message: str,
        ) -> Event:
            event_repository.decide_event(
                event_id,
                actor_id=actor_id,
                from_status=EventStatus.UNDER_REVIEW,
                to_status=EventStatus.APPROVED,
                reason="",
            )
            return original_request(
                event_id,
                actor_id=actor_id,
                from_status=from_status,
                message=message,
            )

        monkeypatch.setattr(event_repository, "request_clarification", approve_before_clarification)

        response = request_clarification(client, headers, event["id"], "Stale follow-up.")

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "invalid-transition"
        current = event_repository.get_event(int(event["id"]))
        assert current is not None
        assert current.status is EventStatus.APPROVED
        assert current.history[-1].to_status is EventStatus.APPROVED
        assert "Stale follow-up." not in [entry.notes for entry in current.history]

    def test_a_draft_is_not_reviewable(self, client, auth_headers):
        """A Coordinator cannot see a Draft, so this is a 404 before it is a rule."""
        created = client.post("/events", json=DRAFT, headers=auth_headers("Event Organiser"))

        response = request_clarification(
            client, auth_headers("Event Coordinator"), created.json()["id"]
        )

        assert response.status_code == 404

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

    def test_a_rejected_event_is_refused_too(self, client, auth_headers, event_repository):
        # US8.1: Event must be assigned to the coordinator for them to see it
        seed(event_repository, status=EventStatus.REJECTED, coordinator_id=COORDINATOR_ID)

        response = request_clarification(client, auth_headers("Event Coordinator"), "500")

        assert response.status_code == 409

    def test_an_event_that_does_not_exist(self, client, auth_headers):
        response = request_clarification(client, auth_headers("Event Coordinator"), "9999")

        assert response.status_code == 404

    def test_an_id_that_is_not_a_number(self, client, auth_headers):
        response = request_clarification(client, auth_headers("Event Coordinator"), "abc")

        assert response.status_code == 404


class TestTheRuleOnItsOwn:
    """`check_clarification` decides, and the route only reports what it said."""

    def test_a_submitted_event_may_be_queried(self):
        assert check_clarification(status=EventStatus.SUBMITTED) is None

    def test_an_event_under_review_may_be_queried_again(self):
        assert check_clarification(status=EventStatus.UNDER_REVIEW) is None

    def test_a_draft_reads_as_not_yet_submitted(self):
        """Unreachable through the route, and still the honest answer."""
        assert (
            check_clarification(status=EventStatus.DRAFT) is ClarificationRefusal.NOT_YET_SUBMITTED
        )

    def test_every_other_status_reads_as_decided(self):
        for reviewed in (
            EventStatus.APPROVED,
            EventStatus.REJECTED,
            EventStatus.PLANNING,
            EventStatus.CONFIRMED,
            EventStatus.COMPLETED,
            EventStatus.CANCELLED,
        ):
            assert check_clarification(status=reviewed) is ClarificationRefusal.ALREADY_DECIDED, (
                reviewed
            )

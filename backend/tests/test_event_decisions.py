"""US7.1 decisions and US4.3's status-transition allowlist."""

import pytest

from app.event_status import EventStatus, transition_allowed
from app.event_store import Event
from app.permissions import Role
from app.users import User
from tests.conftest import COORDINATOR_ID, ORGANISER_ID, SUBMITTABLE_NEEDS

DRAFT = {
    "title": "Faculty Welcome Night",
    "purpose": "Welcome the new intake.",
    "description": "Talks.",
    "startsAt": "2027-11-02T18:00",
    "endsAt": "2027-11-02T21:00",
    "expectedAttendance": 120,
    **SUBMITTABLE_NEEDS,
}


def under_review_event(client, auth_headers) -> dict:
    """Create an event in Under Review status.
    US8.6: Assigns the event to the coordinator before requesting clarification."""
    organiser = auth_headers("Event Organiser")
    created = client.post("/events", json=DRAFT, headers=organiser)
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]
    submitted = client.post(f"/events/{event_id}/submit", headers=organiser)
    assert submitted.status_code == 200, submitted.text

    # US8.6: Assign the event to the coordinator before they can interact with it
    assigned = client.post(
        f"/events/{event_id}/assign",
        json={"coordinatorId": str(COORDINATOR_ID)},
        headers=auth_headers("Event Coordinator Lead"),
    )
    assert assigned.status_code == 200, assigned.text

    reviewed = client.post(
        f"/events/{event_id}/clarification",
        json={"message": "Please confirm the final plan."},
        headers=auth_headers("Event Coordinator"),
    )
    assert reviewed.status_code == 200, reviewed.text
    return reviewed.json()


def decide(client, headers, event_id: str, decision: str, reason: str = "Not feasible."):
    body = {"reason": reason} if decision == "reject" else None
    return client.post(f"/events/{event_id}/{decision}", json=body, headers=headers)


def seeded_event(event_repository, status: EventStatus) -> Event:
    event = Event(
        id=900,
        title="Seeded event",
        purpose="Testing",
        description="",
        starts_at="2027-11-02T18:00",
        ends_at="2027-11-02T21:00",
        expected_attendance=20,
        status=status,
        organiser_id=ORGANISER_ID,
        organiser_name="Dylan",
        created_at="2026-01-01T09:00:00",
        updated_at="2026-01-01T09:00:00",
        coordinator_id=COORDINATOR_ID,
    )
    event_repository.events.append(event)
    return event


class TestTransitionRules:

    def test_every_other_real_transition_is_blocked(self):
        allowed = {
            (EventStatus.DRAFT, EventStatus.SUBMITTED),
            (EventStatus.SUBMITTED, EventStatus.UNDER_REVIEW),
            (EventStatus.UNDER_REVIEW, EventStatus.APPROVED),
            (EventStatus.UNDER_REVIEW, EventStatus.REJECTED),
            # D2: a Rejected event may be resubmitted.
            (EventStatus.REJECTED, EventStatus.SUBMITTED),
            (EventStatus.APPROVED, EventStatus.PLANNING),
            # US4.4: the Pending Safety Check stage.
            (EventStatus.PLANNING, EventStatus.PENDING_SAFETY_CHECK),
            (EventStatus.PENDING_SAFETY_CHECK, EventStatus.CONFIRMED),
            (EventStatus.PENDING_SAFETY_CHECK, EventStatus.PLANNING),
            (EventStatus.CONFIRMED, EventStatus.COMPLETED),
            # US11.3: an accepted important change sends it back to Planning.
            (EventStatus.CONFIRMED, EventStatus.PLANNING),
            # US4.6: anything not already Completed, Cancelled or Rejected.
            *(
                (status, EventStatus.CANCELLED)
                for status in EventStatus
                if status
                not in (EventStatus.COMPLETED, EventStatus.CANCELLED, EventStatus.REJECTED)
            ),
        }
        for before in EventStatus:
            for after in EventStatus:
                expected = before == after or (before, after) in allowed
                assert transition_allowed(from_status=before, to_status=after) is expected



class TestDecisionHappyPaths:
    def test_assigned_coordinator_approves_under_review_event(self, client, auth_headers):
        event = under_review_event(client, auth_headers)

        response = decide(client, auth_headers("Event Coordinator"), event["id"], "approve")

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Approved"

    def test_assigned_coordinator_rejects_with_reason(self, client, auth_headers):
        event = under_review_event(client, auth_headers)

        response = decide(
            client,
            auth_headers("Event Coordinator"),
            event["id"],
            "reject",
            "The safety plan is incomplete.",
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Rejected"
        assert response.json()["history"][-1]["notes"] == "The safety plan is incomplete."

    @pytest.mark.parametrize(
        ("decision", "expected", "notes"),
        [("approve", "Approved", ""), ("reject", "Rejected", "Not feasible.")],
    )
    def test_decision_is_timestamped_and_attributable(
        self, client, auth_headers, decision, expected, notes
    ):
        event = under_review_event(client, auth_headers)

        response = decide(client, auth_headers("Event Coordinator"), event["id"], decision)

        latest = response.json()["history"][-1]
        assert latest == {
            "from": "Under Review",
            "to": expected,
            "at": latest["at"],
            "byId": str(COORDINATOR_ID),
            "byName": "Priya",
            "notes": notes,
            "kind": "",
        }
        assert latest["at"]





class TestDecisionNegativeCases:

    @pytest.mark.parametrize(
        "event_status",
        [
            EventStatus.SUBMITTED,
            EventStatus.APPROVED,
            EventStatus.REJECTED,
            EventStatus.PLANNING,
            EventStatus.CONFIRMED,
            EventStatus.COMPLETED,
            EventStatus.CANCELLED,
        ],
    )
    @pytest.mark.parametrize("decision", ["approve", "reject"])
    def test_only_under_review_can_be_decided(
        self, client, auth_headers, event_repository, event_status, decision
    ):
        event = seeded_event(event_repository, event_status)

        response = decide(client, auth_headers("Event Coordinator"), str(event.id), decision)

        assert response.status_code == 409
        assert response.json()["detail"]["reason"] == "invalid-transition"
        assert event_repository.get_event(event.id).status is event_status
        assert event_repository.get_event(event.id).history == ()

    @pytest.mark.parametrize("reason", ["", "   ", "\n\t"])
    def test_rejection_reason_is_required(self, client, auth_headers, reason):
        event = under_review_event(client, auth_headers)

        response = decide(
            client, auth_headers("Event Coordinator"), event["id"], "reject", reason
        )

        assert response.status_code == 400
        after = client.get(
            f"/events/{event['id']}", headers=auth_headers("Event Organiser")
        ).json()
        assert after["status"] == "Under Review"



    def test_non_assigned_coordinator_cannot_decide(
        self, client, auth_headers, user_store
    ):
        event = under_review_event(client, auth_headers)
        user_store.users.append(
            User(id=10, email="second@spmg3t7.edu", name="Alex", role=Role.COORDINATOR)
        )
        user_store.passwords["second@spmg3t7.edu"] = "Sprint1!demo"
        login = client.post(
            "/auth/login",
            json={"email": "second@spmg3t7.edu", "password": "Sprint1!demo"},
        ).json()

        response = decide(
            client,
            {"Authorization": f"Bearer {login['token']}"},
            event["id"],
            "approve",
        )

        assert response.status_code == 404







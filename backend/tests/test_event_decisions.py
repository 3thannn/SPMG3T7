"""US7.1 decisions and US4.3's status-transition allowlist."""

import pytest

from app.event_status import EventStatus, transition_allowed
from app.event_store import Event
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
    @pytest.mark.parametrize(
        ("before", "after"),
        [
            (EventStatus.DRAFT, EventStatus.SUBMITTED),
            (EventStatus.SUBMITTED, EventStatus.UNDER_REVIEW),
            (EventStatus.UNDER_REVIEW, EventStatus.APPROVED),
            (EventStatus.UNDER_REVIEW, EventStatus.REJECTED),
            (EventStatus.APPROVED, EventStatus.PLANNING),
            # US4.4: the Pending Safety Check stage.
            (EventStatus.PLANNING, EventStatus.PENDING_SAFETY_CHECK),
            (EventStatus.PENDING_SAFETY_CHECK, EventStatus.CONFIRMED),
            (EventStatus.PENDING_SAFETY_CHECK, EventStatus.PLANNING),
            (EventStatus.CONFIRMED, EventStatus.COMPLETED),
            # US11.3: an accepted important change sends it back to Planning.
            (EventStatus.CONFIRMED, EventStatus.PLANNING),
        ],
    )
    def test_allowed_transitions(self, before, after):
        assert transition_allowed(from_status=before, to_status=after)

    def test_every_other_real_transition_is_blocked(self):
        allowed = {
            (EventStatus.DRAFT, EventStatus.SUBMITTED),
            (EventStatus.SUBMITTED, EventStatus.UNDER_REVIEW),
            (EventStatus.UNDER_REVIEW, EventStatus.APPROVED),
            (EventStatus.UNDER_REVIEW, EventStatus.REJECTED),
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

    def test_same_status_is_not_treated_as_a_transition(self):
        assert transition_allowed(
            from_status=EventStatus.UNDER_REVIEW,
            to_status=EventStatus.UNDER_REVIEW,
        )


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

    def test_organiser_can_read_rejection_reason(self, client, auth_headers):
        event = under_review_event(client, auth_headers)
        decide(client, auth_headers("Event Coordinator"), event["id"], "reject", "No capacity.")

        response = client.get(
            f"/events/{event['id']}", headers=auth_headers("Event Organiser")
        )

        assert response.json()["status"] == "Rejected"
        assert response.json()["history"][-1]["notes"] == "No capacity."

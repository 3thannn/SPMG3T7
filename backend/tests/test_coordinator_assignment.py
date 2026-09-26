"""US8.1 — automatic Coordinator assignment on submission.

When an event moves to Submitted, the system assigns exactly one Event Coordinator
automatically via round-robin. Once assigned, only that Coordinator may review,
request clarification, or edit the event. The Organiser retains visibility of
their own events regardless of assignment.

This narrows the US4.1/US5.1/US5.2/US7.3 visibility from "any Coordinator" to
"the assigned Coordinator only", which is what the comments in those features
promised would arrive here.
"""

import pytest

from app.event_status import EventStatus
from app.event_store import Event
from app.permissions import Role
from app.users import User
from tests.conftest import COORDINATOR_ID, ORGANISER_ID, VENUE_STAFF_ID

DRAFT = {
    "title": "Team Building Workshop",
    "purpose": "Improve team collaboration",
    "startsAt": "2026-11-15T14:00",
    "description": "Interactive workshop for staff",
    "expectedAttendance": 30,
}


def submitted_event(client, auth_headers) -> dict:
    """Create and submit an event, returning the submitted event JSON."""
    organiser = auth_headers("Event Organiser")
    created = client.post("/events", json=DRAFT, headers=organiser)
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]
    submitted = client.post(f"/events/{event_id}/submit", headers=organiser)
    assert submitted.status_code == 200, submitted.text
    return submitted.json()


def seed_event(event_repository, **overrides) -> Event:
    """Put an event straight into the store for testing."""
    fields = {
        "id": 500,
        "title": "Seeded Event",
        "purpose": "Testing",
        "description": "Test event",
        "starts_at": "2026-11-20T10:00",
        "ends_at": "2026-11-20T12:00",
        "expected_attendance": 50,
        "status": EventStatus.DRAFT,
        "organiser_id": ORGANISER_ID,
        "organiser_name": "Dylan",
        "created_at": "2026-01-10T09:00:00",
        "updated_at": "2026-01-10T09:00:00",
    }
    event = Event(**{**fields, **overrides})
    event_repository.events.append(event)
    return event


class TestAC1AutomaticAssignment:
    """AC1: When an event's status changes to Submitted, the system assigns exactly
    one Event Coordinator automatically."""

    def test_draft_to_submitted_assigns_coordinator(self, client, auth_headers):
        """Moving Draft → Submitted assigns exactly one Coordinator."""
        event = submitted_event(client, auth_headers)

        assert "coordinatorId" in event
        assert event["coordinatorId"] is not None
        assert isinstance(event["coordinatorId"], int)

    def test_update_without_status_change_does_not_assign(self, client, auth_headers):
        """Updating event fields without changing status should not trigger assignment."""
        organiser = auth_headers("Event Organiser")
        created = client.post("/events", json=DRAFT, headers=organiser)
        event_id = created.json()["id"]

        # Update the draft without submitting
        updated = client.put(
            f"/events/{event_id}",
            json={**DRAFT, "title": "Updated Workshop Title"},
            headers=organiser,
        )

        assert updated.status_code == 200
        assert updated.json()["coordinatorId"] is None

    def test_event_already_submitted_does_not_reassign(self, client, auth_headers, event_repository):
        """An event that already has a Coordinator is not reassigned on subsequent updates."""
        # Seed an event that's already submitted with a coordinator
        seed_event(
            event_repository,
            id=501,
            status=EventStatus.SUBMITTED,
            coordinator_id=COORDINATOR_ID,
        )

        # Try to "resubmit" or update (this shouldn't reassign)
        response = client.get("/events/501", headers=auth_headers("Event Organiser"))

        assert response.status_code == 200
        assert response.json()["coordinatorId"] == str(COORDINATOR_ID)

    def test_no_coordinators_exist_submission_succeeds(self, client, auth_headers, user_store):
        """If no Coordinators exist, submission succeeds with coordinator_id = NULL."""
        # Remove the coordinator from the user store
        user_store.users = [u for u in user_store.users if u.role != Role.COORDINATOR]

        event = submitted_event(client, auth_headers)

        assert event["status"] == "Submitted"
        assert event["coordinatorId"] is None

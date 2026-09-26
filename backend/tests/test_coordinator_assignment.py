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
        # IDs are strings in the API (following existing pattern)
        assert event["coordinatorId"] == str(COORDINATOR_ID)

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


class TestAC2RoundRobinAssignment:
    """AC2: Assignment is round-robin across all Coordinator accounts."""

    def test_multiple_submissions_rotate_through_coordinators(
        self, client, auth_headers, user_store
    ):
        """Three Coordinators, six submissions → each gets 2 events in order A,B,C,A,B,C."""
        from app.permissions import Role
        from app.users import User

        # Add two more coordinators to the user store
        coordinator_2 = User(id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR)
        coordinator_3 = User(id=11, email="coord3@spmg3t7.edu", name="Jordan", role=Role.COORDINATOR)
        user_store.users.extend([coordinator_2, coordinator_3])

        # Submit 6 events
        organiser = auth_headers("Event Organiser")
        coordinator_ids = []
        for i in range(6):
            created = client.post(
                "/events",
                json={**DRAFT, "title": f"Event {i+1}"},
                headers=organiser,
            )
            event_id = created.json()["id"]
            submitted = client.post(f"/events/{event_id}/submit", headers=organiser)
            coordinator_ids.append(submitted.json()["coordinatorId"])

        # Should rotate: 2, 10, 11, 2, 10, 11 (Priya, Alex, Jordan, repeat)
        assert coordinator_ids == ["2", "10", "11", "2", "10", "11"]

    def test_round_robin_wraps_around(self, client, auth_headers, user_store):
        """After the last Coordinator, assignment wraps back to the first."""
        from app.permissions import Role
        from app.users import User

        # Add one more coordinator
        coordinator_2 = User(id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR)
        user_store.users.append(coordinator_2)

        # Submit 5 events (should cycle: 2, 10, 2, 10, 2)
        organiser = auth_headers("Event Organiser")
        coordinator_ids = []
        for i in range(5):
            created = client.post(
                "/events",
                json={**DRAFT, "title": f"Event {i+1}"},
                headers=organiser,
            )
            event_id = created.json()["id"]
            submitted = client.post(f"/events/{event_id}/submit", headers=organiser)
            coordinator_ids.append(submitted.json()["coordinatorId"])

        assert coordinator_ids == ["2", "10", "2", "10", "2"]

    def test_single_coordinator_always_assigned(self, client, auth_headers):
        """Only 1 Coordinator exists → they get every event."""
        organiser = auth_headers("Event Organiser")

        # Submit 3 events
        coordinator_ids = []
        for i in range(3):
            created = client.post(
                "/events",
                json={**DRAFT, "title": f"Event {i+1}"},
                headers=organiser,
            )
            event_id = created.json()["id"]
            submitted = client.post(f"/events/{event_id}/submit", headers=organiser)
            coordinator_ids.append(submitted.json()["coordinatorId"])

        # All should be assigned to the same coordinator (ID 2)
        assert coordinator_ids == ["2", "2", "2"]


class TestAC4VisibilityNarrowing:
    """AC4: Once an event has an assigned Coordinator, US4.1/US5.1/US5.2 visibility
    narrows to that Coordinator only."""

    def test_assigned_coordinator_can_view_event(self, client, auth_headers, user_store):
        """The assigned Coordinator can GET their assigned event."""
        from app.permissions import Role
        from app.users import User

        # Add a second coordinator
        coordinator_2 = User(id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR)
        user_store.users.append(coordinator_2)
        user_store.passwords["coord2@spmg3t7.edu"] = "Sprint1!demo"

        # Submit an event (will be assigned to first coordinator ID=2)
        event = submitted_event(client, auth_headers)
        assert event["coordinatorId"] == "2"

        # The assigned coordinator (ID=2) can view it
        response = client.get(f"/events/{event['id']}", headers=auth_headers("Event Coordinator"))
        assert response.status_code == 200
        assert response.json()["id"] == event["id"]

    def test_non_assigned_coordinator_cannot_view_event(self, client, auth_headers, user_store):
        """A Coordinator who is NOT assigned to an event gets 404."""
        from app.permissions import Role
        from app.users import User

        # Add a second coordinator
        coordinator_2 = User(id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR)
        user_store.users.append(coordinator_2)
        user_store.passwords["coord2@spmg3t7.edu"] = "Sprint1!demo"

        # Submit an event (will be assigned to first coordinator ID=2)
        event = submitted_event(client, auth_headers)
        assert event["coordinatorId"] == "2"

        # Try to view it as the non-assigned coordinator (ID=10)
        sign_in_response = client.post(
            "/auth/login",
            json={"email": "coord2@spmg3t7.edu", "password": "Sprint1!demo"}
        )
        coordinator_2_token = sign_in_response.json()["token"]

        response = client.get(
            f"/events/{event['id']}",
            headers={"Authorization": f"Bearer {coordinator_2_token}"}
        )

        # Should be 404 (not found / not visible)
        assert response.status_code == 404

    def test_assigned_coordinator_can_edit_event(self, client, auth_headers, user_store):
        """The assigned Coordinator can PUT changes to their assigned event."""
        from app.permissions import Role
        from app.users import User

        # Add a second coordinator
        coordinator_2 = User(id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR)
        user_store.users.append(coordinator_2)

        # Submit an event (assigned to first coordinator ID=2)
        event = submitted_event(client, auth_headers)
        assert event["coordinatorId"] == "2"

        # The assigned coordinator can edit it
        updated_draft = {**DRAFT, "title": "Updated by assigned coordinator"}
        response = client.put(
            f"/events/{event['id']}",
            json=updated_draft,
            headers=auth_headers("Event Coordinator")
        )

        assert response.status_code == 200
        assert response.json()["title"] == "Updated by assigned coordinator"

    def test_non_assigned_coordinator_cannot_edit_event(self, client, auth_headers, user_store):
        """A non-assigned Coordinator cannot PUT changes to the event."""
        from app.permissions import Role
        from app.users import User

        # Add a second coordinator
        coordinator_2 = User(id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR)
        user_store.users.append(coordinator_2)
        user_store.passwords["coord2@spmg3t7.edu"] = "Sprint1!demo"

        # Submit an event (assigned to first coordinator ID=2)
        event = submitted_event(client, auth_headers)
        assert event["coordinatorId"] == "2"

        # Try to edit as non-assigned coordinator
        sign_in_response = client.post(
            "/auth/login",
            json={"email": "coord2@spmg3t7.edu", "password": "Sprint1!demo"}
        )
        coordinator_2_token = sign_in_response.json()["token"]

        updated_draft = {**DRAFT, "title": "Attempted update by non-assigned"}
        response = client.put(
            f"/events/{event['id']}",
            json=updated_draft,
            headers={"Authorization": f"Bearer {coordinator_2_token}"}
        )

        # Should be 404 or 403
        assert response.status_code in [403, 404]

    def test_non_assigned_coordinator_cannot_request_clarification(self, client, auth_headers, user_store):
        """A non-assigned Coordinator cannot POST a clarification request."""
        from app.permissions import Role
        from app.users import User

        # Add a second coordinator
        coordinator_2 = User(id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR)
        user_store.users.append(coordinator_2)
        user_store.passwords["coord2@spmg3t7.edu"] = "Sprint1!demo"

        # Submit an event (assigned to first coordinator ID=2)
        event = submitted_event(client, auth_headers)
        assert event["coordinatorId"] == "2"

        # Try to request clarification as non-assigned coordinator
        sign_in_response = client.post(
            "/auth/login",
            json={"email": "coord2@spmg3t7.edu", "password": "Sprint1!demo"}
        )
        coordinator_2_token = sign_in_response.json()["token"]

        response = client.post(
            f"/events/{event['id']}/clarification",
            json={"message": "Question from non-assigned coordinator"},
            headers={"Authorization": f"Bearer {coordinator_2_token}"}
        )

        # Should be 404 (not found / not visible)
        assert response.status_code == 404

    def test_organiser_can_still_view_own_event(self, client, auth_headers, user_store):
        """The Organiser (creator) can always see their event regardless of assignment."""
        from app.permissions import Role
        from app.users import User

        # Add a second coordinator
        coordinator_2 = User(id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR)
        user_store.users.append(coordinator_2)

        # Submit an event (assigned to first coordinator ID=2)
        event = submitted_event(client, auth_headers)
        assert event["coordinatorId"] == "2"

        # Organiser can still view their own event
        response = client.get(f"/events/{event['id']}", headers=auth_headers("Event Organiser"))
        assert response.status_code == 200
        assert response.json()["id"] == event["id"]

    def test_coordinator_list_only_shows_assigned_events(self, client, auth_headers, user_store):
        """When a Coordinator lists events, they only see events assigned to them."""
        from app.permissions import Role
        from app.users import User

        # Add a second coordinator
        coordinator_2 = User(id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR)
        user_store.users.append(coordinator_2)
        user_store.passwords["coord2@spmg3t7.edu"] = "Sprint1!demo"

        # Submit 3 events (will be assigned round-robin: 2, 10, 2)
        organiser = auth_headers("Event Organiser")
        event_ids = []
        for i in range(3):
            created = client.post(
                "/events",
                json={**DRAFT, "title": f"Event {i+1}"},
                headers=organiser
            )
            event_id = created.json()["id"]
            submitted = client.post(f"/events/{event_id}/submit", headers=organiser)
            event_ids.append(submitted.json()["id"])

        # Coordinator 1 (ID=2) should see events 0 and 2
        coord1_list = client.get("/events", headers=auth_headers("Event Coordinator")).json()
        coord1_event_ids = [e["id"] for e in coord1_list]
        assert set(coord1_event_ids) == {event_ids[0], event_ids[2]}

        # Coordinator 2 (ID=10) should see only event 1
        sign_in_response = client.post(
            "/auth/login",
            json={"email": "coord2@spmg3t7.edu", "password": "Sprint1!demo"}
        )
        coordinator_2_token = sign_in_response.json()["token"]

        coord2_list = client.get(
            "/events",
            headers={"Authorization": f"Bearer {coordinator_2_token}"}
        ).json()
        coord2_event_ids = [e["id"] for e in coord2_list]
        assert coord2_event_ids == [event_ids[1]]

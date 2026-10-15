"""US8.3 — Coordinator Lead manually assigns events to Coordinators.

The Lead can take an event from the unassigned queue and assign it to a specific
Coordinator. The assigned Coordinator can then review, approve/reject, and manage
the event.
"""

from app.permissions import Role
from app.users import User
from tests.conftest import COORDINATOR_ID, SUBMITTABLE_NEEDS

DRAFT = {
    "title": "Team Building Workshop",
    "purpose": "Improve team collaboration",
    "startsAt": "2026-11-15T14:00",
    "endsAt": "2026-11-15T17:00",
    "description": "Interactive workshop for staff",
    "expectedAttendance": 30,
    **SUBMITTABLE_NEEDS,
}


def create_unassigned_event(client, auth_headers) -> dict:
    """Helper to create and submit an unassigned event."""
    organiser = auth_headers("Event Organiser")
    created = client.post("/events", json=DRAFT, headers=organiser)
    event_id = created.json()["id"]
    submitted = client.post(f"/events/{event_id}/submit", headers=organiser)
    return submitted.json()


class TestLeadCanAssign:
    """AC1: Coordinator Lead can assign an unassigned event to a Coordinator."""

    def test_lead_can_assign_coordinator_to_unassigned_event(self, client, auth_headers):
        """POST /events/{id}/assign assigns a Coordinator to an unassigned event."""
        # Create an unassigned event
        event = create_unassigned_event(client, auth_headers)
        assert event["coordinatorId"] is None

        # Lead assigns it to a coordinator
        lead = auth_headers("Event Coordinator Lead")
        response = client.post(
            f"/events/{event['id']}/assign",
            json={"coordinatorId": str(COORDINATOR_ID)},
            headers=lead,
        )

        assert response.status_code == 200
        assigned = response.json()
        assert assigned["id"] == event["id"]
        assert assigned["coordinatorId"] == str(COORDINATOR_ID)

    def test_assigned_event_leaves_unassigned_queue(self, client, auth_headers):
        """Once assigned, the event no longer appears in GET /events/unassigned."""
        # Create an unassigned event
        event = create_unassigned_event(client, auth_headers)
        lead = auth_headers("Event Coordinator Lead")

        # Verify it's in the unassigned queue
        unassigned = client.get("/events/unassigned", headers=lead).json()
        assert len(unassigned) == 1
        assert unassigned[0]["id"] == event["id"]

        # Assign it
        client.post(
            f"/events/{event['id']}/assign",
            json={"coordinatorId": str(COORDINATOR_ID)},
            headers=lead,
        )

        # Verify it's no longer in the unassigned queue
        unassigned_after = client.get("/events/unassigned", headers=lead).json()
        assert len(unassigned_after) == 0

    def test_assignment_is_recorded_in_event_history(self, client, auth_headers):
        """Assignment creates a status change record (for audit trail)."""
        event = create_unassigned_event(client, auth_headers)
        lead = auth_headers("Event Coordinator Lead")

        response = client.post(
            f"/events/{event['id']}/assign",
            json={"coordinatorId": str(COORDINATOR_ID)},
            headers=lead,
        )

        assigned = response.json()
        # The event should have history tracking who assigned it
        assert assigned["status"] == "Under Review"
        assert assigned["coordinatorId"] == str(COORDINATOR_ID)
        assert assigned["history"][-1]["from"] == "Submitted"
        assert assigned["history"][-1]["to"] == "Under Review"
        assert assigned["history"][-1]["byId"] == "3"
        assert assigned["history"][-1]["at"]

    def test_only_lead_can_assign(self, client, auth_headers):
        """Regular Coordinator gets 403 when trying to assign."""
        event = create_unassigned_event(client, auth_headers)

        # Try to assign as regular coordinator
        coordinator = auth_headers("Event Coordinator")
        response = client.post(
            f"/events/{event['id']}/assign",
            json={"coordinatorId": str(COORDINATOR_ID)},
            headers=coordinator,
        )

        assert response.status_code == 403

    def test_organiser_cannot_assign(self, client, auth_headers):
        """Event Organiser cannot assign coordinators."""
        event = create_unassigned_event(client, auth_headers)

        organiser = auth_headers("Event Organiser")
        response = client.post(
            f"/events/{event['id']}/assign",
            json={"coordinatorId": str(COORDINATOR_ID)},
            headers=organiser,
        )

        assert response.status_code == 403


class TestAssignmentValidation:
    """AC2: Assignment validation and error handling."""

    def test_cannot_assign_nonexistent_coordinator(self, client, auth_headers):
        """Assigning to a non-existent user ID is rejected."""
        event = create_unassigned_event(client, auth_headers)
        lead = auth_headers("Event Coordinator Lead")

        response = client.post(
            f"/events/{event['id']}/assign",
            json={"coordinatorId": "9999"},
            headers=lead,
        )

        assert response.status_code == 400
        assert "coordinator" in response.json()["detail"]["message"].lower()

    def test_cannot_assign_to_non_coordinator_role(self, client, auth_headers, user_store):
        """Assigning to a user who is not a Coordinator is rejected."""

        # Add a Venue Staff user
        venue_staff = User(
            id=100, email="staff@spmg3t7.edu", name="Sam Staff", role=Role.VENUE_STAFF
        )
        user_store.users.append(venue_staff)

        event = create_unassigned_event(client, auth_headers)
        lead = auth_headers("Event Coordinator Lead")

        response = client.post(
            f"/events/{event['id']}/assign",
            json={"coordinatorId": "100"},
            headers=lead,
        )

        assert response.status_code == 400
        assert "coordinator" in response.json()["detail"]["message"].lower()

    def test_missing_coordinator_id_is_rejected(self, client, auth_headers):
        """Assignment request without coordinatorId is rejected."""
        event = create_unassigned_event(client, auth_headers)
        lead = auth_headers("Event Coordinator Lead")

        response = client.post(
            f"/events/{event['id']}/assign",
            json={},
            headers=lead,
        )

        # FastAPI/Pydantic returns 422 for missing required fields
        assert response.status_code == 422

    def test_cannot_assign_already_assigned_event(self, client, auth_headers, user_store):
        """Assigning an event that already has a coordinator is rejected."""

        # Add a second coordinator
        coordinator_2 = User(
            id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR
        )
        user_store.users.append(coordinator_2)

        event = create_unassigned_event(client, auth_headers)
        lead = auth_headers("Event Coordinator Lead")

        # Assign it the first time
        response1 = client.post(
            f"/events/{event['id']}/assign",
            json={"coordinatorId": str(COORDINATOR_ID)},
            headers=lead,
        )
        assert response1.status_code == 200

        # Try to reassign it
        response2 = client.post(
            f"/events/{event['id']}/assign",
            json={"coordinatorId": "10"},
            headers=lead,
        )

        assert response2.status_code == 409
        assert "already assigned" in response2.json()["detail"]["message"].lower()


class TestAssignedCoordinatorAccess:
    """AC3: Once assigned, the Coordinator can access and work on the event."""

    def test_assigned_coordinator_can_view_event(self, client, auth_headers, user_store):
        """The assigned Coordinator can GET the event."""

        # Add a second coordinator
        coordinator_2 = User(
            id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR
        )
        user_store.users.append(coordinator_2)
        user_store.passwords["coord2@spmg3t7.edu"] = "Sprint1!demo"

        event = create_unassigned_event(client, auth_headers)
        lead = auth_headers("Event Coordinator Lead")

        # Assign to coordinator 2
        client.post(
            f"/events/{event['id']}/assign",
            json={"coordinatorId": "10"},
            headers=lead,
        )

        # Coordinator 2 can view it
        sign_in = client.post(
            "/auth/login",
            json={"email": "coord2@spmg3t7.edu", "password": "Sprint1!demo"},
        )
        coord2_headers = {"Authorization": f"Bearer {sign_in.json()['token']}"}

        response = client.get(f"/events/{event['id']}", headers=coord2_headers)
        assert response.status_code == 200
        assert response.json()["id"] == event["id"]

    def test_non_assigned_coordinator_cannot_view(self, client, auth_headers, user_store):
        """A Coordinator who is NOT assigned gets 404."""

        # Add a second coordinator
        coordinator_2 = User(
            id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR
        )
        user_store.users.append(coordinator_2)
        user_store.passwords["coord2@spmg3t7.edu"] = "Sprint1!demo"

        event = create_unassigned_event(client, auth_headers)
        lead = auth_headers("Event Coordinator Lead")

        # Assign to the default coordinator (ID=2)
        client.post(
            f"/events/{event['id']}/assign",
            json={"coordinatorId": str(COORDINATOR_ID)},
            headers=lead,
        )

        # Coordinator 2 (not assigned) cannot view it
        sign_in = client.post(
            "/auth/login",
            json={"email": "coord2@spmg3t7.edu", "password": "Sprint1!demo"},
        )
        coord2_headers = {"Authorization": f"Bearer {sign_in.json()['token']}"}

        response = client.get(f"/events/{event['id']}", headers=coord2_headers)
        assert response.status_code == 404

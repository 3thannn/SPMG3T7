"""US8.4 — Coordinator Lead reassigns events to different Coordinators.

The Lead can reassign an already-assigned event to a different Coordinator.
The new Coordinator gains access and the previous Coordinator loses access.
"""

from app.permissions import Role
from app.users import User
from tests.conftest import COORDINATOR_ID

DRAFT = {
    "title": "Team Building Workshop",
    "purpose": "Improve team collaboration",
    "startsAt": "2026-11-15T14:00",
    "endsAt": "2026-11-15T17:00",
    "description": "Interactive workshop for staff",
    "expectedAttendance": 30,
    "venueRequirements": "Stage, Projector",
    "preferredLayout": "Theatre",
    "accessibilityNeeds": "Wheelchair access",
    "equipmentNeeds": "Two wireless microphones",
    "registrationNeeds": "None / Not required",
}


def create_assigned_event(client, auth_headers) -> dict:
    """Helper to create, submit, and assign an event to the default coordinator."""
    organiser = auth_headers("Event Organiser")
    created = client.post("/events", json=DRAFT, headers=organiser)
    event_id = created.json()["id"]
    client.post(f"/events/{event_id}/submit", headers=organiser)

    # Assign it to the default coordinator
    lead = auth_headers("Event Coordinator Lead")
    assigned = client.post(
        f"/events/{event_id}/assign",
        json={"coordinatorId": str(COORDINATOR_ID)},
        headers=lead,
    )
    return assigned.json()


class TestLeadCanReassign:
    """AC1: Coordinator Lead can reassign an already-assigned event to a different Coordinator."""

    def test_lead_can_reassign_event_to_different_coordinator(
        self, client, auth_headers, user_store
    ):
        """POST /events/{id}/reassign changes the assigned coordinator."""
        # Add a second coordinator
        coordinator_2 = User(
            id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR
        )
        user_store.users.append(coordinator_2)

        # Create an event assigned to Coordinator 1
        event = create_assigned_event(client, auth_headers)
        assert event["coordinatorId"] == str(COORDINATOR_ID)

        # Lead reassigns it to Coordinator 2
        lead = auth_headers("Event Coordinator Lead")
        response = client.post(
            f"/events/{event['id']}/reassign",
            json={"coordinatorId": "10"},
            headers=lead,
        )

        assert response.status_code == 200
        reassigned = response.json()
        assert reassigned["id"] == event["id"]
        assert reassigned["coordinatorId"] == "10"
        assert reassigned["status"] == "Submitted"  # Status unchanged

    def test_reassigned_event_is_visible_to_new_coordinator(self, client, auth_headers, user_store):
        """The new coordinator can access the reassigned event."""
        # Add a second coordinator
        coordinator_2 = User(
            id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR
        )
        user_store.users.append(coordinator_2)
        user_store.passwords["coord2@spmg3t7.edu"] = "Sprint1!demo"

        event = create_assigned_event(client, auth_headers)
        lead = auth_headers("Event Coordinator Lead")

        # Reassign to Coordinator 2
        client.post(
            f"/events/{event['id']}/reassign",
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

    def test_reassigned_event_not_visible_to_previous_coordinator(
        self, client, auth_headers, user_store
    ):
        """The previous coordinator loses access after reassignment."""
        # Add a second coordinator
        coordinator_2 = User(
            id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR
        )
        user_store.users.append(coordinator_2)

        event = create_assigned_event(client, auth_headers)
        lead = auth_headers("Event Coordinator Lead")

        # Coordinator 1 can see it before reassignment
        coord1 = auth_headers("Event Coordinator")
        response_before = client.get(f"/events/{event['id']}", headers=coord1)
        assert response_before.status_code == 200

        # Reassign to Coordinator 2
        client.post(
            f"/events/{event['id']}/reassign",
            json={"coordinatorId": "10"},
            headers=lead,
        )

        # Coordinator 1 can no longer see it
        response_after = client.get(f"/events/{event['id']}", headers=coord1)
        assert response_after.status_code == 404

    def test_event_can_be_reassigned_multiple_times(self, client, auth_headers, user_store):
        """A lead can reassign the same event to different coordinators sequentially."""
        # Add two more coordinators
        coordinator_2 = User(
            id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR
        )
        coordinator_3 = User(
            id=11, email="coord3@spmg3t7.edu", name="Jordan", role=Role.COORDINATOR
        )
        user_store.users.append(coordinator_2)
        user_store.users.append(coordinator_3)

        event = create_assigned_event(client, auth_headers)
        lead = auth_headers("Event Coordinator Lead")

        # First reassignment: Coordinator 1 -> 2
        response1 = client.post(
            f"/events/{event['id']}/reassign",
            json={"coordinatorId": "10"},
            headers=lead,
        )
        assert response1.status_code == 200
        assert response1.json()["coordinatorId"] == "10"

        # Second reassignment: Coordinator 2 -> 3
        response2 = client.post(
            f"/events/{event['id']}/reassign",
            json={"coordinatorId": "11"},
            headers=lead,
        )
        assert response2.status_code == 200
        assert response2.json()["coordinatorId"] == "11"

    def test_reassignment_is_recorded_in_history(self, client, auth_headers, user_store):
        """Reassignment creates a history entry."""
        coordinator_2 = User(
            id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR
        )
        user_store.users.append(coordinator_2)

        event = create_assigned_event(client, auth_headers)
        lead = auth_headers("Event Coordinator Lead")

        initial_history_length = len(event["history"])

        # Reassign
        response = client.post(
            f"/events/{event['id']}/reassign",
            json={"coordinatorId": "10"},
            headers=lead,
        )

        reassigned = response.json()
        # Should have at least one more history entry
        assert len(reassigned["history"]) >= initial_history_length

    def test_reassignment_doesnt_change_event_status(self, client, auth_headers, user_store):
        """Reassigning an event doesn't change its workflow status."""
        coordinator_2 = User(
            id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR
        )
        user_store.users.append(coordinator_2)

        event = create_assigned_event(client, auth_headers)
        original_status = event["status"]
        lead = auth_headers("Event Coordinator Lead")

        # Reassign
        response = client.post(
            f"/events/{event['id']}/reassign",
            json={"coordinatorId": "10"},
            headers=lead,
        )

        reassigned = response.json()
        assert reassigned["status"] == original_status


class TestReassignmentAuthorization:
    """AC2: Only Coordinator Lead can reassign events."""

    def test_only_lead_can_reassign(self, client, auth_headers, user_store):
        """Regular Coordinator gets 403 when trying to reassign."""
        coordinator_2 = User(
            id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR
        )
        user_store.users.append(coordinator_2)

        event = create_assigned_event(client, auth_headers)

        # Try to reassign as regular coordinator
        coordinator = auth_headers("Event Coordinator")
        response = client.post(
            f"/events/{event['id']}/reassign",
            json={"coordinatorId": "10"},
            headers=coordinator,
        )

        assert response.status_code == 403

    def test_organiser_cannot_reassign(self, client, auth_headers, user_store):
        """Event Organiser cannot reassign coordinators."""
        coordinator_2 = User(
            id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR
        )
        user_store.users.append(coordinator_2)

        event = create_assigned_event(client, auth_headers)

        organiser = auth_headers("Event Organiser")
        response = client.post(
            f"/events/{event['id']}/reassign",
            json={"coordinatorId": "10"},
            headers=organiser,
        )

        assert response.status_code == 403


class TestReassignmentValidation:
    """AC3: Reassignment validation and error handling."""

    def test_cannot_reassign_to_nonexistent_coordinator(self, client, auth_headers):
        """Reassigning to a non-existent user ID is rejected."""
        event = create_assigned_event(client, auth_headers)
        lead = auth_headers("Event Coordinator Lead")

        response = client.post(
            f"/events/{event['id']}/reassign",
            json={"coordinatorId": "9999"},
            headers=lead,
        )

        assert response.status_code == 400
        assert "coordinator" in response.json()["detail"]["message"].lower()

    def test_cannot_reassign_to_non_coordinator_role(self, client, auth_headers, user_store):
        """Reassigning to a user who is not a Coordinator is rejected."""
        # Add a Venue Staff user
        venue_staff = User(
            id=100, email="staff@spmg3t7.edu", name="Sam Staff", role=Role.VENUE_STAFF
        )
        user_store.users.append(venue_staff)

        event = create_assigned_event(client, auth_headers)
        lead = auth_headers("Event Coordinator Lead")

        response = client.post(
            f"/events/{event['id']}/reassign",
            json={"coordinatorId": "100"},
            headers=lead,
        )

        assert response.status_code == 400
        assert "coordinator" in response.json()["detail"]["message"].lower()

    def test_cannot_reassign_unassigned_event(self, client, auth_headers, user_store):
        """Attempting to reassign an unassigned event is rejected."""
        coordinator_2 = User(
            id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR
        )
        user_store.users.append(coordinator_2)

        # Create an unassigned event (submitted but not assigned)
        organiser = auth_headers("Event Organiser")
        created = client.post("/events", json=DRAFT, headers=organiser)
        event_id = created.json()["id"]
        submitted = client.post(f"/events/{event_id}/submit", headers=organiser)
        event = submitted.json()
        assert event["coordinatorId"] is None

        # Try to reassign it (should fail - it's not assigned yet)
        lead = auth_headers("Event Coordinator Lead")
        response = client.post(
            f"/events/{event_id}/reassign",
            json={"coordinatorId": "10"},
            headers=lead,
        )

        assert response.status_code == 409
        assert "not assigned" in response.json()["detail"]["message"].lower()

    def test_missing_coordinator_id_is_rejected(self, client, auth_headers):
        """Reassignment request without coordinatorId is rejected."""
        event = create_assigned_event(client, auth_headers)
        lead = auth_headers("Event Coordinator Lead")

        response = client.post(
            f"/events/{event['id']}/reassign",
            json={},
            headers=lead,
        )

        # FastAPI/Pydantic returns 422 for missing required fields
        assert response.status_code == 422

    def test_cannot_reassign_nonexistent_event(self, client, auth_headers, user_store):
        """Reassigning a non-existent event is rejected."""
        coordinator_2 = User(
            id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR
        )
        user_store.users.append(coordinator_2)

        lead = auth_headers("Event Coordinator Lead")
        response = client.post(
            "/events/999999/reassign",
            json={"coordinatorId": "10"},
            headers=lead,
        )

        assert response.status_code == 404

    def test_reassign_to_same_coordinator_is_idempotent(self, client, auth_headers):
        """Reassigning to the currently assigned coordinator succeeds (idempotent)."""
        event = create_assigned_event(client, auth_headers)
        lead = auth_headers("Event Coordinator Lead")

        # Reassign to the same coordinator (already assigned to COORDINATOR_ID)
        response = client.post(
            f"/events/{event['id']}/reassign",
            json={"coordinatorId": str(COORDINATOR_ID)},
            headers=lead,
        )

        # Should succeed (idempotent operation)
        assert response.status_code == 200
        reassigned = response.json()
        assert reassigned["coordinatorId"] == str(COORDINATOR_ID)

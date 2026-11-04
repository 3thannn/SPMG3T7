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




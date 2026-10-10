"""US8.6 — Row-Level Security: Lead can view all events.

The Coordinator Lead role has broader visibility than regular Coordinators.
While regular Coordinators can only see events assigned to them (US8.1),
the Lead can see ALL events (both assigned and unassigned) to manage assignments.
"""

from app.event_status import EventStatus
from app.permissions import Role
from app.users import User
from tests.conftest import COORDINATOR_ID, ORGANISER_ID

DRAFT = {
    "title": "Team Building Workshop",
    "purpose": "Improve team collaboration",
    "startsAt": "2026-11-15T14:00",
    "description": "Interactive workshop for staff",
    "expectedAttendance": 30,
}


class TestLeadCanViewAll:
    """AC1: Lead can view all events, not just assigned ones."""

    def test_lead_can_view_all_events_including_unassigned(
        self, client, auth_headers, event_repository
    ):
        """Lead can GET /events and see both assigned and unassigned events."""
        from app.event_store import Event

        # Seed an unassigned event and an assigned event
        event_repository.events.extend([
            Event(
                id=501,
                title="Unassigned Event",
                purpose="Testing",
                description="No coordinator",
                starts_at="2026-11-15T14:00",
                ends_at="2026-11-15T16:00",
                expected_attendance=30,
                status=EventStatus.SUBMITTED,
                organiser_id=ORGANISER_ID,
                organiser_name="Dylan",
                created_at="2026-01-10T09:00:00",
                updated_at="2026-01-10T09:00:00",
                coordinator_id=None,
            ),
            Event(
                id=502,
                title="Assigned Event",
                purpose="Testing",
                description="Has coordinator",
                starts_at="2026-11-16T14:00",
                ends_at="2026-11-16T16:00",
                expected_attendance=40,
                status=EventStatus.SUBMITTED,
                organiser_id=ORGANISER_ID,
                organiser_name="Dylan",
                created_at="2026-01-10T10:00:00",
                updated_at="2026-01-10T10:00:00",
                coordinator_id=COORDINATOR_ID,
            ),
        ])

        # Lead can see both events
        response = client.get("/events", headers=auth_headers("Event Coordinator Lead"))

        assert response.status_code == 200
        events = response.json()
        event_ids = {e["id"] for e in events}
        assert "501" in event_ids
        assert "502" in event_ids

    def test_lead_can_view_events_assigned_to_others(
        self, client, auth_headers, event_repository, user_store
    ):
        """Lead can view events assigned to other Coordinators."""
        from app.event_store import Event

        # Add a second coordinator
        coordinator_2 = User(
            id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR
        )
        user_store.users.append(coordinator_2)

        # Seed an event assigned to the second coordinator
        event_repository.events.append(
            Event(
                id=501,
                title="Event Assigned to Coord 2",
                purpose="Testing",
                description="Assigned to Alex",
                starts_at="2026-11-15T14:00",
                ends_at="2026-11-15T16:00",
                expected_attendance=30,
                status=EventStatus.SUBMITTED,
                organiser_id=ORGANISER_ID,
                organiser_name="Dylan",
                created_at="2026-01-10T09:00:00",
                updated_at="2026-01-10T09:00:00",
                coordinator_id=10,
            )
        )

        # Lead can view it
        response = client.get("/events/501", headers=auth_headers("Event Coordinator Lead"))

        assert response.status_code == 200
        event = response.json()
        assert event["id"] == "501"
        assert event["coordinatorId"] == "10"

    def test_regular_coordinator_cannot_view_unassigned_events(
        self, client, auth_headers, event_repository
    ):
        """Regular Coordinator cannot see unassigned events (only Lead can)."""
        from app.event_store import Event

        # Seed an unassigned event
        event_repository.events.append(
            Event(
                id=501,
                title="Unassigned Event",
                purpose="Testing",
                description="No coordinator",
                starts_at="2026-11-15T14:00",
                ends_at="2026-11-15T16:00",
                expected_attendance=30,
                status=EventStatus.SUBMITTED,
                organiser_id=ORGANISER_ID,
                organiser_name="Dylan",
                created_at="2026-01-10T09:00:00",
                updated_at="2026-01-10T09:00:00",
                coordinator_id=None,
            )
        )

        # Regular coordinator cannot see it
        response = client.get("/events", headers=auth_headers("Event Coordinator"))

        assert response.status_code == 200
        events = response.json()
        assert len(events) == 0  # No events visible to regular coordinator

    def test_regular_coordinator_cannot_view_events_assigned_to_others(
        self, client, auth_headers, event_repository, user_store
    ):
        """Regular Coordinator cannot see events assigned to other Coordinators."""
        from app.event_store import Event

        # Add a second coordinator
        coordinator_2 = User(
            id=10, email="coord2@spmg3t7.edu", name="Alex", role=Role.COORDINATOR
        )
        user_store.users.append(coordinator_2)
        user_store.passwords["coord2@spmg3t7.edu"] = "Sprint1!demo"

        # Seed an event assigned to coordinator 1 (ID=2)
        event_repository.events.append(
            Event(
                id=501,
                title="Event Assigned to Coord 1",
                purpose="Testing",
                description="Assigned to Priya",
                starts_at="2026-11-15T14:00",
                ends_at="2026-11-15T16:00",
                expected_attendance=30,
                status=EventStatus.SUBMITTED,
                organiser_id=ORGANISER_ID,
                organiser_name="Dylan",
                created_at="2026-01-10T09:00:00",
                updated_at="2026-01-10T09:00:00",
                coordinator_id=COORDINATOR_ID,
            )
        )

        # Coordinator 2 cannot view it
        sign_in = client.post(
            "/auth/login",
            json={"email": "coord2@spmg3t7.edu", "password": "Sprint1!demo"},
        )
        coord2_headers = {"Authorization": f"Bearer {sign_in.json()['token']}"}

        response = client.get("/events/501", headers=coord2_headers)

        assert response.status_code == 404

"""Coordinator assignment and assigned-event visibility.

When an event moves to Submitted, it waits for Lead assignment. Once assigned,
only that Coordinator may review,
request clarification, or edit the event. The Organiser retains visibility of
their own events regardless of assignment.

This narrows the US4.1/US5.1/US5.2/US7.3 visibility from "any Coordinator" to
"the assigned Coordinator only", which is what the comments in those features
promised would arrive here.
"""


from app.event_status import EventStatus
from app.event_store import Event
from tests.conftest import ORGANISER_ID, SUBMITTABLE_NEEDS

DRAFT = {
    "title": "Team Building Workshop",
    "purpose": "Improve team collaboration",
    "startsAt": "2026-11-15T14:00",
    "endsAt": "2026-11-15T17:00",
    "description": "Interactive workshop for staff",
    "expectedAttendance": 30,
    **SUBMITTABLE_NEEDS,
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




class TestAC2RoundRobinAssignment:
    """AC2: US8.2 - Round-robin is removed. All events remain unassigned on submit."""



    def test_no_auto_assignment_regardless_of_coordinators(self, client, auth_headers):
        """US8.2: Events remain unassigned even when Coordinators exist."""
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

        # US8.2: All remain NULL, not assigned to any coordinator
        assert coordinator_ids == [None, None, None]


